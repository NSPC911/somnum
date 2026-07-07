# somnum

I had a dream. There was a programming language that looked like this

```
5 + 10 >>       # prints 15
10 = 5          # store '5' into 10
5 + 10 >>       # prints 10
```

I couldn't resist the opportunity to implement it, there was no language like it, and I wanted to see if it could be Turing complete.

somnum comes from two words
- somnus, Latin for sleep, because I dreamed it
- num, because it is a language of numbers

## The spec is a program

Because letters are stripped before parsing, letters are free comments, so [`spec.num`](spec.num) is simultaneously the full language specification and a runnable conformance test. Lines containing digits or punctuation are forced into comments with `#`.

```sh
cat spec.stdin | uv run somnum spec.num
```

Running `uv run somnum` with no arguments starts a repl with a persistent number line. Bare expressions are echoed there (in a program they are an error), prompts and errors go to stderr
- typing `exit` does nothing because letters are comments. leave with ctrl-d.

Expected output is pinned in `spec.expected`, and the diff runs as the test suite:

```sh
uv run pytest
```

`examples/` contains a few examples that can be used

- fibonacci.num - prints the first n fibonacci numbers (you need to input a value!)

```
1 <<
11 = @0
12 = @1
13 = @0
!! (13 < @(1)) {
    11 >>           print number
    14 = 11 + 12      get next number
    11 = 12          pass number over
    12 = 14          pass new number
    13 = 13 + @1     increment counter
}
```

- gcd.num - prints the greatest common divisor of two numbers (you need to input two values!)

```
710 = & (0, 1) => (2) {
    ? (1 == @0) {
        2 = 0                  the second number is zero so the first is the answer
    } ??? {
        2 = $710 (1, 0 % 1)    otherwise recurse with the second number and the remainder
    }
}

700 <<
$710 (700, 701) >>
````
