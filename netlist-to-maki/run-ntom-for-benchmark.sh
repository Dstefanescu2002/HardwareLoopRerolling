#!/bin/bash
#   Usage: ./run-loop-id.sh <benchmarks_list>
# Example: ./run-loop-id.sh BENCHMARKS_SMALL

BLIFS=basejump-netlists
RESULTS=results
BENCHMARKS_LIST=$1

[ -d $RESULTS ] && echo "! results dir exists, deleting !" && rm -rf $RESULTS
mkdir $RESULTS

while read benchname; do
        for blif in $BLIFS/$benchname*.blif; do
                name=${blif%.*}
                echo "$name"
                if [[ ! -f $name.rkt ]]; then
		            { time python3 netlist-to-maki-ast.py -pyrtl \
                           $blif ; } &>> $RESULTS/netlist-to-maki.log
	            fi
                echo "-----------"
        done
done <$BENCHMARKS_LIST