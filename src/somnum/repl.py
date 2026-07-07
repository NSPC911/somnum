import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.output.defaults import create_output

from somnum.interp import FNTYPE, Function, Interp, LangError, Parser, tokenize

PROMPT = "#> "
CONTINUE = ".. "


def show(value: object) -> str:
    """Render a slot value for echoing.

    Returns:
        The value as the source text that would produce it.
    """
    if isinstance(value, Function):
        sig = (
            "& ("
            + ", ".join(str(p) for p in value.params)
            + ") => ("
            + str(value.ret)
            + ")"
        )
        if value.locs:
            sig += " ~ (" + ", ".join(str(s) for s in value.locs) + ")"
        return sig + " { }"
    if value is FNTYPE:
        return "&"
    return str(value)


def parse_or_wait(buf: str, force: bool) -> list | None:
    """Parse the buffer unless the input looks unfinished.

    Returns:
        The parsed statements, or None to wait for more lines.

    Raises:
        LangError: When the buffer cannot become valid with more input.
    """
    toks = tokenize(buf)
    depth = sum(t[0] in ("(", "{") for t in toks) - sum(
        t[0] in (")", "}") for t in toks
    )
    if depth > 0 and not force:
        return None
    try:
        return Parser(toks, allow_bare=True).program()
    except LangError as ex:
        ran_out = "EOF" in str(ex) or "unclosed" in str(ex)
        if ran_out and not force:
            return None
        raise


def make_bindings() -> KeyBindings:
    """Build key bindings that only submit once brackets balance.

    Returns:
        Bindings where enter inserts a newline on an unfinished
        statement instead of submitting, so earlier lines stay editable.
    """
    kb = KeyBindings()

    @kb.add("enter")
    def _(event: object) -> None:
        buf = event.current_buffer
        force = buf.document.current_line.strip() == ""
        try:
            stmts = parse_or_wait(buf.document.text, force)
        except LangError:
            stmts = "invalid"
        if stmts is None:
            buf.insert_text("\n")
        else:
            buf.validate_and_handle()

    return kb


def repl() -> None:
    """Read statements forever until end of input."""
    err = sys.stderr
    print("somnum repl", file=err)
    print("letters are comments so typing words does nothing", file=err)
    print("an empty line finishes a hanging statement and ctrl d leaves", file=err)
    interp = Interp()
    # prompt_toolkit gives identical line editing and redraw behavior on
    # every OS, unlike stdlib readline (GNU readline on unix, pyreadline3
    # on windows); prompts render through stderr so piping stdout stays clean.
    # multiline keeps a hanging statement in one editable buffer so earlier
    # lines (like a function's opening brace) can still be revised before
    # the whole thing is submitted.
    interactive = sys.stdin.isatty()
    session = (
        PromptSession(
            output=create_output(stdout=err),
            multiline=True,
            key_bindings=make_bindings(),
            prompt_continuation=CONTINUE,
        )
        if interactive
        else None
    )
    while True:
        try:
            if session is not None:
                text = session.prompt(PROMPT)
            else:
                buf = ""
                while True:
                    err.write(CONTINUE if buf else PROMPT)
                    err.flush()
                    line = input()
                    force = bool(buf) and line.strip() == ""
                    buf = buf + "\n" + line if buf else line
                    if not buf.strip():
                        buf = ""
                        break
                    try:
                        stmts = parse_or_wait(buf, force)
                    except LangError:
                        break
                    if stmts is not None:
                        break
                text = buf
        except EOFError:
            err.write("\n")
            return
        except KeyboardInterrupt:
            err.write("\n")
            continue
        if not text.strip():
            continue
        try:
            stmts = Parser(tokenize(text), allow_bare=True).program()
        except LangError as ex:
            print(f"error: {ex}", file=err)
            continue
        try:
            for stmt in stmts:
                if stmt[0] == "expr":
                    print(show(interp.eval(stmt[1])))
                else:
                    interp.exec(stmt)
        except LangError as ex:
            print(f"error: {ex}", file=err)
        except KeyboardInterrupt:
            print("interrupted", file=err)
