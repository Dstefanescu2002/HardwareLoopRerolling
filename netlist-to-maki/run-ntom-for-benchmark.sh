#!/bin/bash
#   Usage: ./run-loop-id.sh <benchmarks_list>
# Example: ./run-loop-id.sh BENCHMARKS_SMALL

BLIFS=basejump-netlists
RESULTS=results
RESULTS_REROLLED=results_rerolled
BENCHMARKS_LIST=$1

[ -d $RESULTS ] && echo "! results dir exists, deleting !" && rm -rf $RESULTS
mkdir $RESULTS
[ -d $RESULTS_REROLLED ] && echo "! results_rerolled dir exists, deleting !" && rm -rf $RESULTS_REROLLED
mkdir $RESULTS_REROLLED

while read benchname; do
        for blif in $BLIFS/$benchname*.blif; do
                name=${blif%.*}
                echo "$name"
                if [[ ! -f $name.rkt ]]; then
		            { time python3 main.py -pyrtl \
                           $blif ; } &>> $RESULTS/netlist-to-maki.log
	            fi
                echo "-----------"
        done
done <$BENCHMARKS_LIST