---
title: "Prehistoric Programming: War and Peace in 200ms"
date: 2026-03-23
description: "Everyone's gotta start somewhere. Let's learn what a byte is and rip through text like it's 1978"
tags: ["linux", "programming", "c", "performance"]
draft: false
---

I've been reading [The C Programming Language by K & R](https://www.amazon.com/Programming-Language-2nd-Brian-Kernighan/dp/0131103628)

Two chapters in and it's clear that my lack of Freshman CS is gonna sting. All fun and games until we start moving bits around. OK, let's catch up, and make it fast.

This arc was partially inspired by [Casey Muratori's](https://x.com/cmuratori) rants on performant code, and a deep desire to escape LLM type-checked, 8 fallback elifs, 20,000 lines of bloated dashboard hell. I also just, love things that go fast.

Who am I kidding; I use Arch, btw, worship Luke Smith, and voluntarily ran a [Desktop that requires you to recompile whenever you want change a color](https://dwm.suckless.org/). This was a natural next step.

By the end of this post I am poorly attempting to flex on GNU core utils with the speed of my 70 line C program that eats russian literature at ~16 million letters per second.

For now, let's just get something to print.

## Start with one character

```c
#include <stdio.h>

int main(int argc, char *argv[]) {
  int c;

  c = getchar();

  if (c != EOF) {
    printf("%c\n", c);
  }

  return 0;
}
```

Neat. Now, short of plagiarizing Dennis Ritchie's examples or rewriting a GNU core util, let's build something useful. I know, this is ASCII, I am positive I can google or prompt my 4b param model on my phone anything I am about to learn, but after 2 chapters I get the feeling that this binary stuff is going to be on the test.

First decision was to shirk stdin in favor of command line arguments. I envision my future code breaking because of obscure `i=0101101, i++` errors where a step in the wrong direction causes inexplicable downstream behavior. I need a resource to quickref my missing mental model of characters.

We're holding a char `c` in our hands, and we can print it to stdout, but we know that is just a representation of a value. some int, that itself is a friendly abstraction of the number represented as a byte. Let's output that:

## Build the binary column

```c
void print_row(char c) {
  char symbol[8];
  char binary[9];
  int i;

  for (i = 7; i >= 0; i--) {
    binary[7 - i] = ((c >> i) & 1) ? '1' : '0';
  }
  binary[8] = '\0';

  printf("%-8s %-5u 0x%02X   %s\n", symbol, c, c, binary);
}
```

Instantiate a place to put the symbolic output e.g `A` or `SPACE` and then create an array of char with 9 places for our byte of char data. 8 for the ASCII text, and one for the null terminator.

Next we need to read our first bit and walk backwards down our array, pushing the bit to the right with c >> i until we finally set our null terminator.

```zsh
> ./char A
symbol   value hex    binary
A        65    0x41   01000001
```

Wow great this kinda works.

## Control characters need names

The first rough version fell apart on `\n` and `\t`, and I had some constants with a `switch()` but I hated the code. ASCII has a lot more oddball control codes and such than I had ever paid attention to. After looping through 0-127 it seems like 0-31 are mostly special characters that dont print well like `\n` or `ACK`. Barring me discovering some inherent "name" data stuffed into these 8 bits, or a library to do this for me, I had to result to a lookup table:

```c
static const char *ASCII_CONTROL_NAMES[] = {
    "NUL", "SOH", "STX", "ETX", "EOT", "ENQ",  "ACK", "BEL", "BS",
    "HT",  "LF",  "VT",  "FF",  "CR",  "SO",   "SI",  "DLE", "DC1",
    "DC2", "DC3", "DC4", "NAK", "SYN", "ETB",  "CAN", "EM",  "SUB",
    "ESC", "FS",  "GS",  "RS",  "US",  "SPACE"};

static const char *symbol_label(unsigned char c, char symbol[8]) {
  if (c <= 32) {
    return ASCII_CONTROL_NAMES[c];
  }

  if (c == 127) {
    return "DEL";
  }

  if (c <= 126) {
    symbol[0] = (char)c;
    symbol[1] = '\0';
  } else {
    snprintf(symbol, 8, "0x%02X", (unsigned)c);
  }

  return symbol;
}
```

Paired with some optimizations to our initial binary assignment and putting that in its own function outside of printrow(), we can now get consistent formatting when we pass a char, or a set of chars to our program. It's iterating through the characters provided by walking through the bytes.

```zsh
> ./char A
symbol   value hex    binary
A        65    0x41   01000001
> ./char Chan
symbol   value hex    binary
C        67    0x43   01000011
h        104   0x68   01101000
a        97    0x61   01100001
n        110   0x6E   01101110
> ./char "The C Programming Language"
symbol   value hex    binary
T        84    0x54   01010100
h        104   0x68   01101000
e        101   0x65   01100101
SPACE    32    0x20   00100000
C        67    0x43   01000011
```

## Let it read anything

Last thing I want, is to skip the "", get rid of the arguments safety check and just have this thing read any and all text given to it.
And while we're at it let's make sure it can be fed output from a file, that seems useful. Only slightly concerned about flying too close to the sun here. Based on my reading of the code, it should be able to handle _any_ number of characters as long as the shell doesn't break the input first.

```c
int main(int argc, char *argv[]) {
  printf("%-8s %-5s %-6s %s\n", "symbol", "value", "hex", "binary");

  if (argc == 1) {
    if (!isatty(STDIN_FILENO)) {
      int c;

      while ((c = getchar()) != EOF) {
        print_row((unsigned char)c);
      }
    } else {
      for (int i = 0; i < 128; i++) {
        print_row((unsigned char)i);
      }
    }
  } else {
    for (int i = 1; i < argc; i++) {
      if (i > 1) {
        print_row((unsigned char)' ');
      }
      for (int j = 0; argv[i][j] != '\0'; j++) {
        print_row((unsigned char)argv[i][j]);
      }
    }
  }

  return 0;
}
```

For the main function, we print our header row with printf, then handle three major cases. In the event no arguments are provided it will; check for stdin and call printrow() over that, else it will just print our default ASCII table for values 0-127 (great to grep or visualize the relationships). When there is 1 or more argument provided, the shell splits the chars into multiple arguments based on the spaces, so we handle that by, printing a row of SPACE artificially in between each argument, and then continuing to print the row for each byte in the string until we reach the null terminator. This effectively makes it so `./char A B CC` creates the same output as `./char "A B CC"`.

```zsh
> ./char A B 'CC'
symbol   value hex    binary
A        65    0x41   01000001
SPACE    32    0x20   00100000
B        66    0x42   01000010
SPACE    32    0x20   00100000
C        67    0x43   01000011
C        67    0x43   01000011
```

OK yea that's sick. and fast.

## Benchmarks

```zsh
> wc char.c
  71  229 1564 char.c
```

71 lines, not too shabby. Let's feed it itself, see if the program can handle new lines, quotes and C syntax.

```zsh
> ./char < char.c
symbol   value hex    binary
#       35    0x23   00100011
i        105   0x69   01101001
n        110   0x6E   01101110
c        99    0x63   01100011
l        108   0x6C   01101100
u        117   0x75   01110101
d        100   0x64   01100100
e        101   0x65   01100101
SPACE    32    0x20   00100000
<        60    0x3C   00111100
s        115   0x73   01110011
```

#### do it got a hemi?

```zsh
>  hyperfine --warmup 1000 --input char.c './char'
Benchmark 1: ./char
  Time (mean ± σ):     123.6 µs ±  81.1 µs    [User: 208.8 µs, System: 134.3 µs]
  Range (min … max):    61.5 µs … 831.9 µs    4251 runs
```

#### µs......

Light travels 37km in the time it takes for our compiled code to parse itself. That's 23 meters per byte parsed.

![Gonna Need a Bigger Boat](/boat.webp)

#### We are gonna need a bigger boat.jpg

Now I understand why Jeff Geerling spent the past year of his life procuring clocks.

```zsh
> ls -lah war_and_peace.txt
Permissions Size User Date Modified Name
.rw-r--r--  3.4M chan  2 Mar 04:30   war_and_peace.txt

> wc war_and_peace.txt
  66041  566333 3359613 war_and_peace.txt

```

Thank you project gutenberg, 3mil char should do.

Half of me wants to download 40TB llm training dataset off of hugging face but we'll have to settle for some open source Russian Literature.

```zsh
> hyperfine --warmup 30 './char < war_and_peace.txt'
Benchmark 1: ./char < war_and_peace.txt
  Time (mean ± σ):     239.7 ms ±   1.4 ms    [User: 237.2 ms, System: 2.0 ms]
  Range (min … max):   237.9 ms … 241.9 ms    12 runs
```

240 milliseconds. Couldn't be more pleased. We aren't solving world hunger or loading up pandas to reverse a string, I know the code is simple, but that's the point right? We learned how to interact with the basic blocks in a way that's widely applicable and blazing fast. It's doing slightly more than just adding a tick to a counter, it's producing meaningful output in hopefully an efficient way, and helped me get comfortable with the syntax and some basic ideas of C.

```zsh
> ./char < war_and_peace.txt | sed -n '1,2p;150000,150009p'
symbol   value hex    binary
0xEF     239   0xEF   11101111
n        110   0x6E   01101110
i        105   0x69   01101001
c        99    0x63   01100011
e        101   0x65   01100101
SPACE    32    0x20   00100000
c        99    0x63   01100011
l        108   0x6C   01101100
e        101   0x65   01100101
a        97    0x61   01100001
n        110   0x6E   01101110
```

_....nice, clean_

No actually. That is the 150,000th char in [War and Peace](https://www.gutenberg.org/cache/epub/2600/pg2600.txt). Clone and try yourself, that was my first run, those exact 9 char.

Also, did you catch that? The 1st byte? We asked for it with `sed -n 1` and it returned the symbol 0xEF. That's not a letter... ah, yes. As expected. This is a Unicode. A UTF-8 Byte Order Mark, telling anything reading the file to expect unicode. Of course, 8 bits leaves 256 possible int values that can be represented, and our code only covers 0-127, the ASCII set. We'll have to address UTF-8 another time.

## Comparisons

![bateman.jpg](/American-Psycho.jpg)

#### Let's see Paul Allen's card....

wc, the glorified +1 machine, absolutely smokes me.

```zsh
> hyperfine --warmup 30 'wc war_and_peace.txt'
Benchmark 1: wc war_and_peace.txt
  Time (mean ± σ):       7.4 ms ±   0.3 ms    [User: 7.0 ms, System: 0.5 ms]
  Range (min … max):     7.0 ms …   8.9 ms    384 runs
```

cat is even worse. orders of magnitude.

```zsh
> hyperfine -N --warmup 30 'cat war_and_peace.txt'
Benchmark 1: cat war_and_peace.txt
  Time (mean ± σ):     283.8 µs ±  58.3 µs    [User: 203.3 µs, System: 55.4 µs]
  Range (min … max):   239.0 µs … 1058.4 µs    7363 runs
```

In an attempt to optimize, I recompiled `char.c` with `gcc -03 -march=native` and was able to shave off 40ms. Further optimizations would require making the code less fun, like not formatting the bytes each loop, and I have elected to ignore those implementations in the name of science.

```zsh
> hyperfine --warmup 30 --input war_and_peace.txt './char'
Benchmark 1: ./char
  Time (mean ± σ):     199.3 ms ±   3.6 ms    [User: 196.9 ms, System: 1.8 ms]
  Range (min … max):   195.8 ms … 207.2 ms    15 runs
```

#### Sub 200ms. Count it.

Would Casey be proud for a Day 1 program? Or at this scale it's all trivial; I should try doing something actually complex before I start flexing online about solving the software performance crisis. Seems like I should put down K+R and read the source for `cat`

## Next steps

The rust rewrite is calling me. My first attempt did not handle memory correctly and showed me just how efficient this C program is.

As for our current program, the last column is intriguing. It looks... fast. I wonder what all we can do with it. Potentially group repeated phrases, build some compression, and then maybe a tokenizer from scratch??? We'll see.

Or maybe I've wasted a day, C will soon be an artifact only found in computer science museums and we will just feed War and Peace into Claude directly to vibe spew a table of binary and hex of 3 million bytes.

So it goes.

[git repo](https://github.com/herboh/ascii)
