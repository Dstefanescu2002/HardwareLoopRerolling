from collections import defaultdict
import pyrtl
import copy
import math
import pyrtl
import sys
from suffixarray import suffix_array, lcp_array, tandem_repeats
import signal
import copy

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
                'array-store': 'array-store',
                'array-ref': 'array-ref'
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
        elif self.op in ['Register', 'Input', 'Output']:
            return '({} {})'.format(op, self.args[1])
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

# Tokenize a Maki IR AST.
# Recurisvely walks the AST;
# primarily considers WireVector expression operators.
def ast_to_tokens(ast):
    if isinstance(ast, Block):
        cmds = ()
        for c in ast.cmds:
            cmds += (ast_to_tokens(c),)
        return cmds
    elif isinstance(ast, DefCmd):
        # lhs rhs
        lhs = ast_to_tokens(ast.lhs)
        rhs = ast_to_tokens(ast.rhs)
        return (lhs, rhs)
    elif isinstance(ast, AssignCmd):
        # lhs rhs
        if isinstance(ast.lhs, Wire):
            lhs = str(ast.lhs.bitwidth) + ast.lhs.type
        else:
            lhs = ast_to_tokens(ast.lhs)
        rhs = ast_to_tokens(ast.rhs)
        return (lhs, rhs)
    elif isinstance(ast, ForCmd):
        body = ast_to_tokens(ast.body)
        return ('LOOPSTART',) + body + ('LOOPEND',)
    elif isinstance(ast, WireExp):
        # op args
        argtokens = [ast_to_tokens(a) for a in ast.args]
        argtokens = '-'.join(a for a in argtokens if a != '')
        op = {
                '+': '+',
                '-': '-',
                '*': '*',
                '&': '&',
                '|': '|',
                '^': '^',
                '=': '=',
                '<': '<',
                '>': '>',
                'n': 'n',
                '~': '~',
                'x': 'x',
                'c': 'c',
                'Input': 'I',
                'Output': 'O',
                'Register': 'R',
                'Const': 'C',
                's': 's',
                'r': 'r',
                'w': 'w',
                'm': 'm',
                '@': '@',
        }[ast.op]
        return '{}'.format(op) + (argtokens if ast.op in 'csx' else \
                argtokens.translate({ord(i): None for i in argtokens if i in 'C'}))
    elif isinstance(ast, Wire):
        # ignore
        return ''
    elif isinstance(ast, WireSlice):
        # vexps
        vexps = ','.join(ast_to_tokens(v) for v in ast.vexps)
        return '({})'.format(vexps)
    elif isinstance(ast, ValExp):
        return ''
    elif isinstance(ast, Var):
        # ignore
        return ''
    elif isinstance(ast, VarIndex):
        # ignore
        return ''
    elif isinstance(ast, VarSlice):
        # ignore
        return ''
    elif isinstance(ast, Literal):
        # ignore
        return ''
    else:
        return ''

# Translate Maki IR AST to concrete syntax ingestible by Racket tool
def ir_to_racket(ast, netlist_name):
    var = dict() # var name -> uint
    vid = 0

    # sv-gen
    internal_signals = dict()

    inputs = ''
    inputsn = 0
    outputs = ''
    outputsn = 0
    registers = ''
    registersn = 0
    removeCmds = set()
    def mapVarToNum(ast, vid):
        for c in ast.cmds:
            if isinstance(c, (AssignCmd, DefCmd)):
                if not str(c.lhs.name) in var:
                    var[str(c.lhs.name)] = vid
                    if isinstance(c.lhs, Wire):
                        internal_signals[vid] = c.lhs.bitwidth
                    vid += 1
                c.lhs.name = var[str(c.lhs.name)]
            elif isinstance(c, ForCmd):
                var[str(c.index)] = vid
                internal_signals[vid] = c.lhs.bitwidth
                vid += 1
                c.index = var[str(c.index)]
                vid = mapVarToNum(c.body, vid)
        return vid
    mapVarToNum(ast, vid)

    return var

def tokens_to_string(tokens):
    s = ''
    for t in tokens:
        s += '{}{}{} '.format(t[0], t[1], str(t[2:]) if len(t) > 2 else '')
    return s

# From a tokenized Maki AST, returns a maximal tandem repeat.
# Relies on suffixarray library.
def get_tandem_repeats_from_tokens(s):
    sa = suffix_array(s)
    lcp = lcp_array(s, sa)

    tandems = tandem_repeats(s, sa, lcp)
    max_repeater = ''
    for k,v in tandems.items():
        str_ops = ''.join([str(w[1]) for w in k])
        str_ops = str_ops.translate({ord(i): None for i in str_ops if i in ' ,'})
        str_IOR = str_ops.translate({ord(i): None for i in str_ops if i not in 'IORCwr'})

        if str_IOR and str_ops == len(str_IOR) * str_IOR[0]:
            continue
        if not str_ops:
            continue
        elif v[1] < 3:
            continue
        elif not max_repeater:
            max_repeater = k
            continue
        elif v[1] > tandems[max_repeater][1]:
            max_repeater = k
        elif v[1] == tandems[max_repeater][1] and v[0] > tandems[max_repeater][0]:
            max_repeater = k
        elif v[1] == tandems[max_repeater][1] and len(k) > len(max_repeater):
            max_repeater = k

    if not max_repeater:
        return (None,None,None)

    start = tandems[max_repeater][0]
    length = len(max_repeater) * tandems[max_repeater][1]
    return (tandems[max_repeater][0], len(max_repeater), tandems[max_repeater][1])
    # Returns (start-of-loop, length-of-rerolled-loop-body, number-of-repeats)

# Identifies a loop candidate from a tokenized Maki program.
# Note: This returns the maximal loop candidate;
# this function is intended to be called repeatedly
# until all viable/interesting loop candidates are found.
# (See `blif-benchmark.py` find_loops() for an example.)
def loop_id(ast):

    tok = ast_to_tokens(ast)

    s,l,r = get_tandem_repeats_from_tokens(tok)
    # Returns (start-of-loop, length-of-rerolled-loop-body, number-of-repeats)
    if not s:
        return (None, ast)

    startCmd = s
    lengthCmd = l
    endCmd = startCmd + lengthCmd * r

    pre = Block(ast.cmds[0:startCmd])

    loop = Block(ast.cmds[startCmd:startCmd + lengthCmd * 1]) # first iteration

    post = Block(ast.cmds[endCmd:])

    ports = 0
    for c in pre.cmds:
        if isinstance(c, DefCmd):
            if isinstance(c.rhs, WireExp):
                if c.rhs.op == 'Input':
                    ports += 1
                elif c.rhs.op == 'Output':
                    ports += 1
                elif c.rhs.op == 'Register':
                    ports += 1
                else:
                    continue

    return ([(loop.cmds[0].body.cmds[0].lhs.name if isinstance(loop.cmds[0], ForCmd) else loop.cmds[0].lhs.name),l,r], Block(pre.cmds + [ForCmd(Literal(ast.newHole()), Literal(r), Block(loop.cmds))] + post.cmds))


def find_loops(ir, varMap):

    def timeout_handler(signum, frame):
        raise TimeoutException()

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(3600)

    loops = []
    try:
        while True:
            newLoop, ir = loop_id(ir)
            if not newLoop:
                break
            newLoop[0] = varMap[str(newLoop[0])]
            loops += [newLoop]
        loops.sort(key=lambda x: x[0] + (x[1] * x[2]))
    except TimeoutException:
        print("Loop identifier timeout!")
        return loops
    signal.alarm(0)
    return loops

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
                            cmds[j].rhs.args[ai] = WireExp('s', [copy.deepcopy(x) for x in c.rhs.args])
                            removeSels.add(c)
    for r in removeSels:
        cmds.remove(r)

    return Block(cmds)


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
        