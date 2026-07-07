import sys
from typing import Any

# a token is (type, value, line) and ast nodes are nested tagged tuples
Token = tuple[str, Any, int]
Node = tuple[Any, ...]


class LangError(Exception):
    pass


class Function:
    __slots__ = ("params", "ret", "locs", "body")

    def __init__(
        self, params: list[int], ret: int, locs: list[int], body: list[Node]
    ) -> None:
        self.params = params
        self.ret = ret
        self.locs = locs
        self.body = body


FNTYPE = object()  # value of a bare &, used only for <> type checks

OPS3 = [">>>", ">->", "???"]
OPS2 = [">>", "->", "<<", "<-", "=>", "<=", ">=", "<>", "==", "!=", "??", "!!"]
OPS1 = set("=+-*/%^(){},@$&~?!<>")


def tokenize(src: str) -> list[Token]:
    toks = []
    for ln, raw in enumerate(src.splitlines(), 1):
        line = raw.split("#", 1)[0]
        line = "".join(c for c in line if not c.isalpha())
        i = 0
        while i < len(line):
            c = line[i]
            if c in " \t\r":
                i += 1
                continue
            # a minus immediately followed by a digit is a sign, not subtraction
            if c.isdigit() or (
                c == "-" and i + 1 < len(line) and line[i + 1].isdigit()
            ):
                j = i + 1
                while j < len(line) and line[j].isdigit():
                    j += 1
                toks.append(("INT", int(line[i:j]), ln))
                i = j
                continue
            matched = None
            for op in OPS3 + OPS2:
                if line.startswith(op, i):
                    matched = op
                    break
            if matched:
                toks.append((matched, matched, ln))
                i += len(matched)
                continue
            if c in OPS1:
                toks.append((c, c, ln))
                i += 1
                continue
            raise LangError(f"line {ln}: stray character {c!r}")
    toks.append(("EOF", None, toks[-1][2] if toks else 0))
    return toks


class Parser:
    def __init__(self, toks: list[Token], allow_bare: bool = False) -> None:
        self.toks = toks
        self.i = 0
        # the repl echoes bare expressions instead of rejecting them
        self.allow_bare = allow_bare

    def peek(self) -> str:
        return self.toks[self.i][0]

    def line(self) -> int:
        return self.toks[self.i][2]

    def next(self) -> Token:
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, ty: str) -> Token:
        t = self.next()
        if t[0] != ty:
            raise LangError(f"line {t[2]}: expected {ty} but found {t[0]}")
        return t

    def program(self) -> list[Node]:
        stmts = []
        while self.peek() != "EOF":
            stmts.append(self.statement())
        return stmts

    def block(self) -> list[Node]:
        self.expect("{")
        stmts = []
        while self.peek() != "}":
            if self.peek() == "EOF":
                raise LangError(f"line {self.line()}: unclosed block")
            stmts.append(self.statement())
        self.next()
        return stmts

    def statement(self) -> Node:
        line = self.line()
        match self.peek():
            case "?":
                return self.if_statement()
            case "!":
                return self.loop_statement()
            case "!!":
                return self.while_statement()
        expr = self.expr()
        match (nt := self.peek()):
            case "=":
                self.next()
                return ("assign", self.as_addr(expr, line), self.expr(), line)
            case ">>" | "->":
                self.next()
                return ("out", nt, expr, line)
            case ">>>" | ">->":
                self.next()
                return ("tapeout", nt, self.as_addr(expr, line), line)
            case "<<" | "<-":
                self.next()
                return ("input", nt, self.as_addr(expr, line), line)
            case "~":
                self.next()
                return ("forget", self.as_addr(expr, line), line)
        if expr[0] != "call" and not self.allow_bare:
            raise LangError(
                f"line {line}: a bare expression that is not a call does nothing and is an error"
            )
        return ("expr", expr, line)

    def as_addr(self, expr: Node, ln: int) -> Node:
        # an address is a plain number or an @( ) computed value
        match expr[0]:
            case "slot":
                return ("num", expr[1])
            case "num":
                return expr
            case "at":
                return expr[1]
        raise LangError(f"line {ln}: this needs an address (a plain number or @(...))")

    def if_statement(self) -> Node:
        ln = self.line()
        self.expect("?")
        self.expect("(")
        cond = self.expr()
        self.expect(")")
        arms = [(cond, self.block())]
        els = None
        while self.peek() == "??":
            self.next()
            self.expect("(")
            c = self.expr()
            self.expect(")")
            arms.append((c, self.block()))
        if self.peek() == "???":
            self.next()
            els = self.block()
        return ("if", arms, els, ln)

    def loop_statement(self) -> Node:
        ln = self.line()
        self.expect("!")
        self.expect("(")
        count = self.expr()
        self.expect(")")
        self.expect("(")
        var = self.as_addr(self.expr(), ln)
        self.expect(")")
        return ("loop", count, var, self.block(), ln)

    def while_statement(self) -> Node:
        ln = self.line()
        self.expect("!!")
        self.expect("(")
        cond = self.expr()
        self.expect(")")
        return ("while", cond, self.block(), ln)

    def expr(self) -> Node:
        left = self.additive()
        if self.peek() in ("==", "!=", "<", ">", "<=", ">=", "<>"):
            op = self.next()[0]
            return ("bin", op, left, self.additive())
        return left

    def additive(self) -> Node:
        left = self.term()
        while self.peek() in ("+", "-"):
            op = self.next()[0]
            left = ("bin", op, left, self.term())
        return left

    def term(self) -> Node:
        left = self.power()
        while self.peek() in ("*", "/", "%"):
            op = self.next()[0]
            left = ("bin", op, left, self.power())
        return left

    def power(self) -> Node:
        b = self.primary()
        if self.peek() == "^":
            self.next()
            return ("bin", "^", b, self.power())
        return b

    def primary(self) -> Node:
        t = self.peek()
        ln = self.line()
        if t == "INT":
            return ("slot", self.next()[1])
        if t == "@":
            self.next()
            if self.peek() == "INT":
                return ("num", self.next()[1])
            if self.peek() == "(":
                self.next()
                e = self.expr()
                self.expect(")")
                return ("at", e)
            raise LangError(
                f"line {ln}: @ needs a number or a parenthesized expression"
            )
        if t == "(":
            self.next()
            e = self.expr()
            self.expect(")")
            return e
        if t == "$":
            self.next()
            if self.peek() == "INT":
                addr = ("num", self.next()[1])
            elif self.peek() == "@":
                self.next()
                self.expect("(")
                addr = self.expr()
                self.expect(")")
            else:
                raise LangError(f"line {ln}: $ needs a slot number or @(...)")
            self.expect("(")
            args = []
            if self.peek() != ")":
                args.append(self.expr())
                while self.peek() == ",":
                    self.next()
                    args.append(self.expr())
            self.expect(")")
            return ("call", addr, args, ln)
        if t == "~":
            self.next()
            if self.peek() == "INT":
                addr = ("num", self.next()[1])
            elif self.peek() == "@":
                self.next()
                self.expect("(")
                addr = self.expr()
                self.expect(")")
            else:
                raise LangError(f"line {ln}: ~ needs a slot number or @(...)")
            return ("innocent", addr, ln)
        if t == "&":
            return self.func_or_type()
        raise LangError(f"line {ln}: unexpected {t}")

    def func_or_type(self) -> Node:
        ln = self.line()
        self.expect("&")
        if self.peek() != "(":
            return ("fntype",)
        self.next()
        params = self.intlist(")")
        self.expect(")")
        self.expect("=>")
        self.expect("(")
        if self.peek() == ")":
            raise LangError(f"line {ln}: a function must return exactly one slot")
        ret = self.expect("INT")[1]
        self.expect(")")
        locs = []
        if self.peek() == "~":
            self.next()
            self.expect("(")
            locs = self.intlist(")")
            self.expect(")")
        body = self.block()
        if len(set(params)) != len(params):
            raise LangError(f"line {ln}: a slot is repeated in the parameter list")
        for s in params + [ret] + locs:
            if s < 0:
                raise LangError(
                    f"line {ln}: a signature cannot declare a negative slot"
                )
        # scratch overlapping a parameter or the return slot is a noop
        locs = [x for x in dict.fromkeys(locs) if x not in params and x != ret]
        return ("fn", params, ret, locs, body)

    def intlist(self, end: str) -> list[int]:
        xs = []
        if self.peek() == end:
            return xs
        xs.append(self.expect("INT")[1])
        while self.peek() == ",":
            self.next()
            xs.append(self.expect("INT")[1])
        return xs


class Interp:
    def __init__(self) -> None:
        self.env: dict[int, Any] = {}

    def run(self, stmts: list[Node]) -> None:
        for s in stmts:
            self.exec(s)

    def exec(self, s: Node) -> None:
        k = s[0]
        if k == "assign":
            _, addr, rhs, ln = s
            self.env[self.addr(addr, ln)] = self.eval(rhs)
        elif k == "out":
            _, mode, e, ln = s
            v = self.eval(e)
            if not isinstance(v, int):
                raise LangError(f"line {ln}: only numbers can be printed")
            print(v if mode == ">>" else self.tochar(v, ln))
        elif k == "tapeout":
            _, mode, addr, ln = s
            a = self.addr(addr, ln)
            vals = []
            while a in self.env and isinstance(self.env[a], int):
                vals.append(self.env[a])
                a += 1
            if mode == ">->":
                print("".join(self.tochar(v, ln) for v in vals))
            else:
                print(" ".join(str(v) for v in vals))
        elif k == "input":
            _, mode, addr, ln = s
            a = self.addr(addr, ln)
            try:
                line = sys.stdin.readline()
            except KeyboardInterrupt:
                raise LangError(f"line {ln}: interrupted while reading stdin")
            if line == "":
                raise LangError(f"line {ln}: expected a line on stdin")
            line = line.rstrip("\n")
            if mode == "<<":
                try:
                    vals = [int(x) for x in line.split()]
                except ValueError:
                    raise LangError(
                        f"line {ln}: stdin line must be space separated integers"
                    )
            else:
                vals = [ord(c) for c in line]
            for i, v in enumerate(vals):
                self.env[a + i] = v
        elif k == "if":
            _, arms, els, ln = s
            for cond, body in arms:
                v = self.eval(cond)
                if not isinstance(v, int) or v != 0:
                    self.run(body)
                    return
            if els is not None:
                self.run(els)
        elif k == "loop":
            _, count, var, body, ln = s
            n = self.num(self.eval(count), ln)
            v = self.addr(var, ln)
            i = 0
            while i < n:
                self.env[v] = i
                self.run(body)
                i += 1
        elif k == "forget":
            _, addr, ln = s
            self.env.pop(self.addr(addr, ln), None)
        elif k == "while":
            _, cond, body, ln = s
            while True:
                v = self.eval(cond)
                if isinstance(v, int) and v == 0:
                    break
                self.run(body)
        elif k == "expr":
            self.eval(s[1])

    def addr(self, node: Node, ln: int) -> int:
        a = self.eval(node)
        if not isinstance(a, int):
            raise LangError(f"line {ln}: an address must be a number")
        if a < 0:
            raise LangError(f"line {ln}: negative slots cannot be addressed")
        return a

    def tochar(self, v: Any, ln: int) -> str:
        if not isinstance(v, int) or v < 0 or v > 0x10FFFF:
            raise LangError(f"line {ln}: {v} is not a valid character code")
        return chr(v)

    def num(self, v: Any, ln: int) -> int:
        if not isinstance(v, int):
            raise LangError(f"line {ln}: a function cannot be used in arithmetic")
        return v

    def typeof(self, v: Any) -> str:
        return "fn" if isinstance(v, Function) or v is FNTYPE else "num"

    def eval(self, e: Node) -> Any:
        k = e[0]
        if k == "slot":
            return self.env.get(e[1], e[1])
        if k == "num":
            return e[1]
        if k == "at":
            return self.eval(e[1])
        if k == "fn":
            return Function(e[1], e[2], e[3], e[4])
        if k == "innocent":
            _, addr, ln = e
            a = self.eval(addr)
            if not isinstance(a, int):
                raise LangError(f"line {ln}: an address must be a number")
            # negative slots can never be assigned so they are innocent forever
            return 1 if a not in self.env else 0
        if k == "fntype":
            return FNTYPE
        if k == "bin":
            op = e[1]
            a = self.eval(e[2])
            b = self.eval(e[3])
            if op == "<>":
                return 1 if self.typeof(a) == self.typeof(b) else 0
            if op == "==":
                return 1 if a is b or a == b else 0
            if op == "!=":
                return 1 if a is not b and a != b else 0
            self.num(a, 0)
            self.num(b, 0)
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                if b == 0:
                    raise LangError("division by zero")
                q = abs(a) // abs(b)
                return -q if (a < 0) != (b < 0) else q
            if op == "%":
                if b == 0:
                    raise LangError("modulo by zero")
                r = abs(a) % abs(b)
                return -r if a < 0 else r
            if op == "^":
                if b < 0:
                    raise LangError("negative exponents are not allowed")
                return a**b
            if op == "<":
                return 1 if a < b else 0
            if op == ">":
                return 1 if a > b else 0
            if op == "<=":
                return 1 if a <= b else 0
            if op == ">=":
                return 1 if a >= b else 0
        if k == "call":
            _, addr, args, ln = e
            a = self.addr(addr, ln)
            f = self.env.get(a, a)
            if not isinstance(f, Function):
                raise LangError(f"line {ln}: slot {a} does not hold a function")
            if len(args) != len(f.params):
                raise LangError(
                    f"line {ln}: function at slot {a} takes "
                    f"{len(f.params)} arguments but got {len(args)}"
                )
            vals = [self.eval(x) for x in args]
            declared = list(dict.fromkeys(f.params + [f.ret] + f.locs))
            saved = {s: (s in self.env, self.env.get(s)) for s in declared}
            for p, v in zip(f.params, vals):
                self.env[p] = v
            if f.ret not in f.params:
                self.env.pop(f.ret, None)
            for loc in f.locs:
                self.env.pop(loc, None)
            try:
                self.run(f.body)
                result = self.env.get(f.ret, f.ret)
            finally:
                for slot, (was_set, val) in saved.items():
                    if was_set:
                        self.env[slot] = val
                    else:
                        self.env.pop(slot, None)
            return result
        raise LangError(f"internal error: unknown node {k}")


def main() -> None:
    if len(sys.argv) == 1:
        from somnum.repl import repl

        repl()
        return
    if len(sys.argv) != 2:
        print("usage: somnum [program.num]", file=sys.stderr)
        sys.exit(2)
    try:
        with open(sys.argv[1]) as fh:
            src = fh.read()
    except FileNotFoundError:
        print(f"error: file {sys.argv[1]} not found", file=sys.stderr)
        raise SystemExit(1)
    except PermissionError:
        print(f"error: file {sys.argv[1]} cannot be read", file=sys.stderr)
        raise SystemExit(1)
    try:
        Interp().run(Parser(tokenize(src)).program())
    except LangError as ex:
        print(f"error: {ex}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
