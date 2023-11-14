# Loop Rerolling for Hardware Decompilation

## Background
Our project is an extension to a previous paper on Hardware Decompilation, presented here: http://hardekbc.github.io/files/sisco23loop.pdf

The approach to synthesizing a program with loops from a linearized version created using a toposort over the netlist graph that is described in this paper consists of three separate steps:
* Loop identification in python using clone detection
* Data flow passes to generate an initial sketch
* SMT solver based CEGIS to fill the sketch in racket

We believe that an alternative, Programming by Demonstration approach to loop rerolling can unify this approach and improve the solution in several key ways:
* Support rerolling of nested loops
* Guarantee that the synthesized HDL program is closest to the original HDL program
* Drastically improve the synthesis time

## Approach
