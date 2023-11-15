from collections import defaultdict
import pyrtl
import copy
import math
import pyrtl
import sys

import signal

class TimeoutException(Exception):
    pass

# AST for abstractly representing Maki IR
class AST:
    _fields = ()
    def __init__(self, *args): #, line=None):
        self.HOLES = 0
        self.HOLE = 'h_'
        for n,x in zip(self._fields, args):
            setattr(self, n, x)

    def newHole(self):
        name = self.HOLE + str(self.HOLES)
        self.HOLES += 1
        return name

# Subclasses of AST for defining each component in the IR
class Block(AST):
    _fields = ('cmds',)
    def __str__(self):
        return '\n'.join(str(c) for c in self.cmds)

class DefCmd(AST):
    _fields = ('lhs', 'rhs')
    def __str__(self):
        return '({0} {1})'.format(str(self.lhs), str(self.rhs))

class AssignCmd(AST):
    _fields = ('lhs', 'rhs')
    def __str__(self):
        return '({0} (<<= {1}))'.format(str(self.lhs), str(self.rhs))

class ForCmd(AST):
    _fields = ('index', 'range', 'body')
    def __str__(self):
        return '({0} (for-range {0} {1} (loop-body\n{2})))'.format(str(self.index), str(self.range), str(self.body))

class WireExp(AST):
    _fields = ('op', 'args')
    def __str__(self):
        op = {
                '+': 'w+',
                '-': 'w-',
                '*': 'w*',
                '&': 'w&',
                '|': 'w||',
                '^': 'w^',
                '=': 'w=',
                '<': 'w<',
                '>': 'w>',
                'n': 'wn',
                '~': 'w~',
                'x': 'wx',
                'c': 'wc',
                'Input': 'Input',
                'Output': 'Output',
                'Register': 'Register',
                'Const': 'bv-const',
                'MemBlock': 'mem-block-create',
                'RomBlock': 'rom-block-create',
                's': 'ws',
                'r': '',
                'w': '<w=',
                'm': 'wm',
                '@': 'w@',
            }[self.op]

        if self.op in '+-*&|^=<>n':
            arg0 = str(self.args[0])
            arg1 = str(self.args[1])
            return '({} {} {})'.format(op, arg0, arg1)
        elif self.op in '~':
            arg0 = str(self.args[0])
            return '({} {})'.format(op, arg0)
        elif self.op in 'c':
            args = ' '.join(str(a) for a in self.args)
            return '({} (list {}))'.format(op, args)
        elif self.op in 's':
            arg0 = str(self.args[0])
            arg1 = str(self.args[1])
            if isinstance(self.args[1], WireSlice):
                return '({} {} (list {}))'.format(op, arg0, arg1)
            return '({} {} {})'.format(op, arg0, arg1)
        elif self.op in 'x':
            arg0 = str(self.args[0])
            arg1 = str(self.args[1])
            arg2 = str(self.args[2])
            return '({} {} {} {})'.format(op, arg0, arg1, arg2)
        elif self.op == 'Const':
            arg0 = str(self.args[0])
            arg1 = str(self.args[1])
            return '({} {} {})'.format(op, arg0, arg1)
        elif self.op in 'r':
            return str(self.args[0])
        elif self.op in 'w':
            return '({} {})'.format(op, str(self.args[0]))
        elif self.op in 'm':
            args = ' '.join(str(a) for a in self.args)
            return '({} {})'.format(op, args)
        elif self.op in '@':
            args = ' '.join(str(a) for a in self.args)
            return '({} {})'.format(op, args)
        else:
            args = ' '.join(str(a) for a in self.args)
            return '({} {})'.format(op, args)

class Wire(AST):
    _fields = ('name', 'bitwidth', 'type')
    def __str__(self):
        return '{0}'.format(str(self.name))

class WireSlice(AST):
    _fields = ('vexps',)
    def __str__(self):
        return '{0}'.format(' '.join(str(x) for x in self.vexps))

class ValExp(AST):
    _fields = ('op', 'args')
    def __str__(self):
        args = ' '.join('(list {})'.format(' '.join(str(y) for y in x)) \
                if isinstance(x, list) \
                else str(x) for x in self.args)
        return '({0} {1})'.format(str(self.op), args)

class Var(AST):
    _fields = ('name', 'slice')
    def __str__(self):
        return '{0}'.format(str(self.name))

class VarIndex(AST):
    _fields = ('value',)
    def __str__(self):
        return '[{0}]'.format(str(self.value)) if self.value else ''

class VarSlice(AST):
    _fields = ('lhs', 'rhs')
    def __str__(self):
        return '[{0}:{1}]'.format(str(self.lhs), str(self.rhs)) if self.lhs or self.rhs else ''

class Literal(AST):
    _fields = ('value',)
    def __str__(self):
        return str(self.value)

class ArrayCreate(AST):
    _fields = ('size',)
    def __str__(self):
        return '(array-create ' + str(self.size) + ')'

# Dataflow analysis over Maki IR Block.
# Returns list of WireVector variable definitions.
def defsInBlock(block):
    defs = []
    for c in block.cmds:
        if isinstance(c, DefCmd) or isinstance(c, AssignCmd):
            if isinstance(c.lhs, Wire) or isinstance(c.lhs, Var):
                defs.append(str(c.lhs))
        elif isinstance(c, ForCmd):
            defs += defsInBlock(c.body)
    return defs

# Dataflow analysis over Maki IR Block.
# Returns dictionary of WireVector variables to uses in the Block.
def usesInBlock(block):
    uses = defaultdict(list)
    for c in block.cmds:
        if isinstance(c, DefCmd) or isinstance(c, AssignCmd):
            uses[str(c.lhs)] = []
            if isinstance(c.rhs, Wire) or isinstance(c.rhs, Var):
                uses[str(c.rhs)].append(str(c.lhs))
            elif isinstance(c.rhs, WireExp) or isinstance(c.rhs, ValExp):
                for a in c.rhs.args:
                    uses[str(a)].append(str(c.lhs))
    return uses

# Translate PyRTL netlist to Maki IR AST.
# Starts with top-level declarations (Inputs, Outputs, Registers, Memories),
# then proceeds to WireVector assignments.
def netlist_to_ast(defs, foldSelects=True):
    # gather all tmps
    tmps = []
    # gather all regs
    regs = []
    # gather all ins
    ins = []
    # gather all outs
    outs = []
    # gather all consts
    consts = []
    # gather all mem writes and memblock/rom declarations
    # need memid, data width, addr width
    mems = []
    memids = dict()
    for w, n in defs.items():
        # if w is Integer, then it is memid, and thus mem write
        if isinstance(w, int):
            mems.append((w, n))
            continue
        if w._code == 'I':
            ins.append((w,n))
        elif w._code == 'O':
            outs.append((w, n))
        elif w._code == 'R':
            regs.append((w, n))
        elif w._code == 'C':
            consts.append((w, n))
        else:
            tmps.append((w, n))

    for w,n in defs.items():
        if not isinstance(w, int) and w._code == 'W':
            regNames = [r.name for r,x in regs]
            for a in n.args:
                if a._code == 'R' and a.name not in regNames:
                    regs.append((a,None))
                    regNames.append(a.name)

    tmps.sort(key=lambda x: int(x[0].name[3:]) if x[0].name[:3] == 'tmp' else x[0].name)
    regs.sort(key=lambda x: int(x[0].name[3:]) if x[0].name[:3] == 'tmp' else x[0].name)

    # move all mem reads to the front first
    memreads = []
    for i,defpair in enumerate(tmps):
        w,n = defpair
        if n.op == 'm':
            memreads.append(i)
    for i in memreads:
        defpair = tmps.pop(i)
        tmps.insert(0, defpair)

    # Consider `tmp_i` and `tmp_j` with i < j. I assumed this implied that
    # `tmp_i` is defined _before_ `tmp_j`. This is sometimes true, but not always.
    # One example is the `demultiplexer` benchmark. One solution is to first do
    # the monotonic ordering. Then, do a basic def-use analysis of temp wire
    # definitions---noting when a definition uses a wire that has not been defined
    # yet. After noting this, repair by moving the missing definition later.
    def findNotDefs():
        defd = {}
        fixes = {}
        for i,defpair in enumerate(tmps):
            w,n = defpair
            defd[w.name] = n
            for a in n.args:
                if a._code == 'W' and a.name not in defd:
                    fixes[a.name] = w.name
        return fixes

    worklist = findNotDefs()
    def timeout_handler(signum, frame):
        raise TimeoutException()

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(3600)
    try:
        while worklist:
            for k,v in worklist.items():
                for i,defpair in enumerate(tmps):
                    w,_ = defpair
                    if w._code == 'W' and w.name == k:
                        for j,fixpair in enumerate(tmps):
                            if fixpair[0].name == v:
                                fixdef = tmps.pop(j)
                                tmps.insert(i, fixdef)
            worklist = findNotDefs()
    except TimeoutException:
        print("Definition rewrite timeout.")
    signal.alarm(0)


    cmds = []
    # init wires
    for w,_ in ins:
        cmds.append(DefCmd(
                Wire(Literal(w.name), Literal(w.bitwidth), 'I'),
                WireExp('Input', [Literal(w.name), Literal(w.bitwidth)])))
    for w,_ in outs:
        cmds.append(DefCmd(
                    Wire(Literal(w.name), Literal(w.bitwidth), 'O'),
                    WireExp('Output', [Literal(w.name), Literal(w.bitwidth)])))
    for w,_ in regs:
        cmds.append(DefCmd(
                    Wire(Literal(w.name), Literal(w.bitwidth), 'R'),
                    WireExp('Register', [Literal(w.name), Literal(w.bitwidth)])))

    postPreambleIndex = len(cmds)

    dedup_consts = set()
    for w,_ in consts:
        const = str(w)
        const_val = const[const.rfind('_') + 1:const.find('/')]
        if "'b" in const_val:
            const_val = const_val[:const_val.find("'b")]
        name = 'const_' + const_val + '_' + str(w.bitwidth)
        dedup_consts.add((name, const_val, w.bitwidth))
    for name,val,width in dedup_consts:
        cmds.append(DefCmd(
                    Wire(Literal(name), Literal(width), 'C'),
                    WireExp('Const', [Literal(val), Literal(width)])))
    const_index = len(cmds)

    for i,net in mems:
        if i not in memids:
            memids[i] = str(i) + '_' + str(net.op_param[1].name)
            cmds.append(DefCmd(
                    Var(memids[i],[]),
                    ValExp('mem-block-create', [Literal(net.args[1].bitwidth), Literal(net.args[0].bitwidth)])))

    for w,n in tmps + regs + outs + mems:
        if isinstance(w, int):
            lhs = Var(memids[n.op_param[0]],[])
        else:
            lhs = Wire(Literal(w.name), Literal(w.bitwidth), w._code)
        if not n:
            continue
        op = n.op

        args = []
        for a in n.args:
            name = None
            width = None
            if a._code == 'C':
                const = str(a)
                const_val = const[const.rfind('_') + 1:const.find('/')]
                if "'b" in const_val:
                    const_val = const_val[:const_val.find("'b")]
                name = Literal('const_' + const_val + '_' + str(a.bitwidth))
                width = Literal(a.bitwidth)
            else:
                name = Literal(a.name)
                width = Literal(a.bitwidth)
            if not name or not width:
                continue
            args.append(Wire(name, width, a._code))

        if op == 's':
            zeroExtendBits = 0
            for a in n.op_param:
                if a == 0:
                    zeroExtendBits += 1
                else:
                    zeroExtendBits = 0
                    break
            if zeroExtendBits > 0 and args[0].type == 'C':
                cname = str(args[0].name)
                val = cname[cname.find('_') + 1 : cname.rfind('_')]
                op = 'Const'
                args = [Literal(val), Literal(zeroExtendBits)]
                cmds.insert(const_index, DefCmd(lhs, WireExp(op, args)))
                continue
            else:
                slices = [a for a in n.op_param]
                monotone = False
                s = slices[0]
                for i in range(1,len(slices)):
                    if s >= slices[i]:
                        monotone = False
                        break
                    monotone = True
                    s = slices[i]
                if monotone:
                    low = Literal(str(slices[0]))
                    high = Literal(str(slices[-1] + 1))
                    args.append(ValExp('arange', [low, high]))
                else:
                    args.append(WireSlice([a for a in n.op_param]))

        if op == 'm' and n.op_param[0] not in memids and isinstance(n.op_param[1], pyrtl.MemBlock):
            i = n.op_param[0]
            memids[i] = str(i) + '_' + str(n.op_param[1].name)
            cmds.insert(postPreambleIndex, DefCmd(
                    Var(memids[i],[]),
                    ValExp('mem-block-create',
                        [Literal(n.dests[0].bitwidth),
                         Literal(n.args[0].bitwidth)])))
            args.insert(0, Var(memids[i],[]))
        elif op == 'm' and n.op_param[0] not in memids and isinstance(n.op_param[1], pyrtl.RomBlock):
            i = n.op_param[0]
            memids[i] = str(i) + '_' + str(n.op_param[1].name)
            data = ['(??)'] * 2**int(n.args[0].bitwidth) if callable(n.op_param[1].data) \
                          else [Literal(x) for x in n.op_param[1].data]
            cmds.insert(postPreambleIndex, DefCmd(
                    Var(memids[i],[]),
                    ValExp('rom-block-create',
                        [Literal(n.dests[0].bitwidth),
                         Literal(n.args[0].bitwidth),
                         data])))
            args.insert(0, Var(memids[i],[]))

        rhs = WireExp(op, args)

        cmds.append(AssignCmd(lhs, args[0]) if (n.op in 'rw' and w.name in [x[0].name for x in outs+regs]) else DefCmd(lhs, rhs))

    netdefs = defsInBlock(Block(cmds))
    netuses = usesInBlock(Block(cmds))

    removeConsts = set()
    # replace const wires with Const expressions inlined
    for i,c in enumerate(cmds):
        if isinstance(c, (DefCmd, AssignCmd)) \
                and isinstance(c.rhs, WireExp) \
                and c.rhs.op == 'Const':
            for j,useCmd in enumerate(cmds):
                if isinstance(useCmd, (DefCmd, AssignCmd)) \
                        and isinstance(useCmd.rhs, WireExp):
                    for ai,arg in enumerate(useCmd.rhs.args):
                        if str(c.lhs) == str(arg):
                            cmds[j].rhs.args[ai] = WireExp('Const', c.rhs.args)
            removeConsts.add(c)
    for r in removeConsts:
        cmds.remove(r)

    removeConsts = set()
    for i,c in enumerate(cmds):
        if isinstance(c, (DefCmd, AssignCmd)) \
                and isinstance(c.rhs, WireExp) \
                and c.rhs.op == 'c' \
                and ['Const']*len(c.rhs.args) == [a.op for a in c.rhs.args if isinstance(a,WireExp)]:
            for j,useCmd in enumerate(cmds):
                if isinstance(useCmd, (DefCmd, AssignCmd)) \
                        and isinstance(useCmd.rhs, WireExp):
                    for ai,arg in enumerate(useCmd.rhs.args):
                        if str(c.lhs) == str(arg):
                            const_string = ''
                            final_width = 0
                            for a in c.rhs.args:
                                val = int(str(a.args[0]))
                                const_string = const_string + bin(val).replace('0b','')
                                final_width += int(str(a.args[1]))
                            constwire = pyrtl.Const(str(final_width) + "'b" + const_string)
                            cmds[j].rhs.args[ai] = WireExp('Const', [Literal(str(constwire.val)), Literal(str(constwire.bitwidth))])
            removeConsts.add(c)
    for r in removeConsts:
        cmds.remove(r)

    if not foldSelects:
        return Block(cmds)

    # NOTE: fold select's with direct references to input wires or regs, then remove those temps
    removeSels = set()
    for i,c in enumerate(cmds):
        if isinstance(c, (DefCmd)) \
                and isinstance(c.rhs, WireExp) \
                and c.rhs.op == 's' \
                and str(c.rhs.args[0]) in [i[0].name for i in (ins + regs + tmps)]:
            for j,useCmd in enumerate(cmds):
                if isinstance(useCmd, (DefCmd)) \
                        and isinstance(useCmd.rhs, WireExp):
                    for ai,arg in enumerate(useCmd.rhs.args):
                        if str(c.lhs) == str(arg):
                            cmds[j].rhs.args[ai] = WireExp('s', c.rhs.args)
                            removeSels.add(c)
    for r in removeSels:
        cmds.remove(r)

    return Block(cmds)

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
    print (og_netlist)
    db_netlist = convert_to_debruijn(og_netlist)
    with open('results/' + bench[18:-4] + 'txt', 'w') as f:
        f.write("wires: {}, nets: {}".format(len(pyrtl.working_block().wirevector_set), len(pyrtl.working_block().logic)) + "\n")
        f.write(str(db_netlist))
    return db_netlist

def convert_to_debruijn(netlist):
    
    var = {}

    def renameVarUses(c, argOp, argIndex, cur_index):
        if isinstance(c, (AssignCmd, DefCmd)):
            renameVarUses(c.rhs, None, None, cur_index)
            return
        if isinstance(c, (WireExp, ValExp)):
            for i,a in enumerate(c.args):
                renameVarUses(a, c.op, i, cur_index)
            return
        if isinstance(c, (Wire, Var)) and str(c.name) in var:
            if (argOp == 'array-ref' and argIndex == 0):
                c.name = '{}'.format(var[str(c.name)] - cur_index)
            elif argOp == 's' and argIndex == 0:
                c.name = '{}'.format(var[str(c.name)] - cur_index)
            elif argOp == 's' and argIndex and argIndex > 0:
                c.name = '(& {})'.format(var[str(c.name)] - cur_index)
            elif argOp in ['a+','a-','a*','a/','a%']:
                c.name = '(& {})'.format(var[str(c.name)] - cur_index)
            else:
                c.name = '{}'.format(var[str(c.name)] - cur_index)
            return
        if isinstance(c, WireSlice):
            for h in c.vexps:
                renameVarUses(h, 's', None, cur_index)
            return
        if isinstance(c, ForCmd):
            for b in c.body.cmds:
                renameVarUses(b, None, None, cur_index)
            return
        return

    for index, cmd in enumerate(netlist.cmds):
        if isinstance(cmd, (DefCmd, AssignCmd)):
            var[cmd.lhs.name.value] = index
            renameVarUses(cmd, None, None, index)
            cmd.lhs.name.value = index
        else:
            renameVarUses(cmd, None, None, index)
        # 
    return netlist
        

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
