from collections import defaultdict
import pyrtl
import copy
import math
import pyrtl
import sys
import signal
from netlistToMaki import netlist_to_ast, convert_to_debruijn, ir_to_racket, find_loops
from rerollLoops import reroll_loops

# Given a PyRTL netlist (bench),
# translate it to Maki AST and run loop identification over it (find_loops()).
# Finally, write the concrete Maki IR with loop candidates annotated to a file.
def do_analysis(bench, format):
    defs, uses = pyrtl.working_block().net_connections(include_virtual_nodes=True)
    memwrites = dict()
    for x in pyrtl.working_block().logic:
        if x.op == '@':
            memwrites[x.op_param[0]] = x
    defs = {**defs, **memwrites}

    og_netlist = netlist_to_ast(defs)
    convert_to_debruijn(og_netlist)
    # ir = copy.deepcopy(og_netlist)
    varMap = ir_to_racket(og_netlist, bench)

    loops = find_loops(og_netlist, varMap)
    # Returns (start-of-loop, length-of-rerolled-loop-body, number-of-repeats)
    
    with open('results/' + bench[18:-4] + 'txt', 'w') as f:
        # f.write("wires: {}, nets: {}".format(len(pyrtl.working_block().wirevector_set), len(pyrtl.working_block().logic)) + "\n")
        f.write(str(og_netlist))
        f.write('\n' + str(loops))

    rerolled_netlist = reroll_loops(og_netlist, loops)

    with open('results_rerolled/' + bench[18:-4] + 'txt', 'w') as f:
        # f.write("wires: {}, nets: {}".format(len(pyrtl.working_block().wirevector_set), len(pyrtl.working_block().logic)) + "\n")
        f.write(str(rerolled_netlist))

    return og_netlist

# Given a BLIF file, import the netlist into PyRTL,
# run some optimizations over it to remove undriven/unused wires,
# and finally start the loop identification process (do_analysis()).
def run_benchmark(bench, clock, format):
    with open(bench) as f:
        blif = f.read()
    pyrtl.input_from_blif(blif, clock_name=clock)

    srcs, dsts = pyrtl.working_block().net_connections()
    dest_set = set(srcs.keys())
    arg_set = set(dsts.keys())
    full_set = dest_set | arg_set
    connected_minus_allwires = full_set.difference(pyrtl.working_block().wirevector_set)
    all_input_and_consts = pyrtl.working_block().wirevector_subset((pyrtl.Input, pyrtl.Const))
    allwires_minus_connected = pyrtl.working_block().wirevector_set.difference(full_set)
    allwires_minus_connected = allwires_minus_connected.difference(all_input_and_consts)
    for w in allwires_minus_connected:
        print("not",w)
        pyrtl.working_block().remove_wirevector(w)

    #print(pyrtl.working_block())
    pyrtl.combine_slice_concats()
    return do_analysis(bench, format)

if __name__ == '__main__':
    if len(sys.argv) - 1 < 2:
        print(help_text)
        exit(1)

    format = sys.argv[1]
    if format not in ('-pyrtl', '-sv'):
        print(help_text)
        exit(1)

    clock = 'clk'
    if len(sys.argv) - 1 == 3:
        clock = sys.argv[3]

    blif_filename = sys.argv[2]
    print('\nRunning benchmark:', blif_filename)
    netlist = run_benchmark(blif_filename, clock, format)
    exit(0)
