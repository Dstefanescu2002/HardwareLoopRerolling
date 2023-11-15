# Netlist to Maki Conversion

## Converting a single netlist
Use the netlist-to-maki-ast.py script, including the following arguements: [-pyrtl / -svl] [path of file for conversion]

## Converting many netlists
Use the run-ntom-for-benchmark.sh script, including the following arguement: [benchmark to be run (usally 'benchmarks/BENCHMARKS-SMALL')]

## Sample Commands
python3 netlist-to-maki-ast.py -pyrtl basejump-netlists/bsg_1_to_n_tagged_num_out_p_32.blif
./run-ntom-for-benchmark.sh benchmarks/BENCHMARKS-SMALL