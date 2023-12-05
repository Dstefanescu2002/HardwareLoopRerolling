from netlistToMaki import ForCmd, Block, AssignCmd, DefCmd, Wire, Var, WireExp, ValExp, WireSlice, VarIndex, ArrayCreate, Literal
import copy

def reroll_loops(maki_prog, loops):
    for loop in loops:
        prog_with_loop = insert_loop(maki_prog, loop[0], loop[1], loop[2])
        return prog_with_loop

def fix_inner_deps(for_cmd, for_start, og_maki_prog):
    og_block = og_maki_prog
    og_maki_prog = og_maki_prog.cmds
    body = for_cmd.body.cmds
    to_add = []
    added = {}
    to_fix = []

    def fix_var(var, var_next, cur_index, c):
        if abs(int(var)) >= cur_index and var == var_next:
            origional_var = og_maki_prog[for_start + cur_index + int(var)].lhs.name
            if origional_var in added:
                return -cur_index - added[origional_var] - 1
            new_dist = -cur_index - len(to_add) - 2
            to_add.append(DefCmd(Var('none', ''), (for_start + cur_index + int(var)) - (for_start - len(to_add))) )
            added[origional_var] = len(to_add) - 1
            return new_dist
        elif (abs(int(var)) >= cur_index):
            to_fix.append(c)
        return var
            
            
    def renameVarUses(c, c_next, argOp, argIndex, cur_index):
        if isinstance(c, (AssignCmd, DefCmd)):
            renameVarUses(c.rhs, c_next.rhs, None, None, cur_index)
            return
        if isinstance(c, (WireExp, ValExp)):
            for i,a in enumerate(c.args):
                renameVarUses(a, c_next.args[i], c.op, i, cur_index)
            return
        if isinstance(c, (Wire, Var)):
            if (argOp == 'array-ref' and argIndex == 0):
                c.name = '{}'.format(fix_var(c.name, c_next.name, cur_index, c))
            elif argOp == 's' and argIndex == 0:
                c.name = '{}'.format(fix_var(c.name, c_next.name, cur_index, c))
            elif argOp == 's' and argIndex and argIndex > 0:
                c.name = '(& {})'.format(fix_var(c.name, c_next.name, cur_index, c))
            elif argOp in ['a+','a-','a*','a/','a%']:
                c.name = '(& {})'.format(fix_var(c.name, c_next.name, cur_index, c))
            else:
                c.name = '{}'.format(fix_var(c.name, c_next.name, cur_index, c))
            return
        if isinstance(c, WireSlice):
            if c_next.vexps[0] != c.vexps[0]:
                c.vexps[0] = for_cmd.index
            for i, h in enumerate(c.vexps):
                renameVarUses(h, c_next.vexps[i], 's', None, cur_index)
            return
        if isinstance(c, ForCmd):
            for i, b in enumerate(c.body.cmds):
                renameVarUses(b, c.body.cmds[i], None, None, cur_index)
            return
        return
    
    for i, cmd in enumerate(body):
        renameVarUses(cmd, og_maki_prog[for_start + i + len(body)], None, None, i)
    
    for c in to_fix:
        c.name = str(int(c.name) - len(to_add) - 1)

    for c in to_add:
        insert_cmd(og_block, for_start, c)
    
    return (to_add, og_block)

def insert_cmd(maki_prog, index, cmd):

    def add_one(var, ref_index, cur_index):
        if int(var) + cur_index < ref_index:
            return int(var) - 1
        return int(var)

    def edit_debruijn_index(c, argOp, argIndex, ref_index, cur_index):
        if isinstance(c, (AssignCmd, DefCmd)):
            edit_debruijn_index(c.rhs, None, None, ref_index, cur_index)
            return
        if isinstance(c, (WireExp, ValExp)):
            for i,a in enumerate(c.args):
                edit_debruijn_index(a, c.op, i, ref_index, cur_index)
            return
        if isinstance(c, (Wire, Var)):
            if (argOp == 'array-ref' and argIndex == 0):
                c.name = '{}'.format(add_one(c.name, ref_index, cur_index))
            elif argOp == 's' and argIndex == 0:
                c.name = '{}'.format(add_one(c.name, ref_index, cur_index))
            elif argOp == 's' and argIndex and argIndex > 0:
                c.name = '(& {})'.format(add_one(c.name, ref_index, cur_index))
            elif argOp in ['a+','a-','a*','a/','a%']:
                c.name = '(& {})'.format(add_one(c.name, ref_index, cur_index))
            else:
                c.name = '{}'.format(add_one(c.name, ref_index, cur_index))
            return
        if isinstance(c, WireSlice):
            # if c_next.vexps[0] != c.vexps[0]:
            #     c.vexps[0] = for_cmd.index
            for i, h in enumerate(c.vexps):
                edit_debruijn_index(h, 's', None, ref_index, cur_index)
            return
        if isinstance(c, ForCmd):
            for i, b in enumerate(c.body.cmds):
                edit_debruijn_index(b, None, None, ref_index, cur_index)
            return
        return

    maki_prog.cmds = maki_prog.cmds[:index] + [cmd] + maki_prog.cmds[index:]
    for i in range(index + 1, len(maki_prog.cmds)):
        edit_debruijn_index(maki_prog.cmds[i], None, None, index, i)

def fix_after_deps(maki_prog, for_cmd, for_start):
    loop_size = len(for_cmd.body.cmds)
    loop_iters = for_cmd.range
    loop_end = for_start + (loop_size * loop_iters)

    new_arrays = []
    new_array_inserts = []
    new_array_lines = set()

    def fix_var(var, cur_index, c):
        index = cur_index + int(var) + (loop_size*loop_iters - (1))
        if index >= for_start and index < for_start + (loop_size * loop_iters):
            which_iter = 0
            current = for_start
            for i in range(loop_iters):
                current += loop_size
                if current > index:
                    which_iter = i
                    spot = index - (current-loop_size)
                    break
            if (spot in new_array_lines):
                return
            new_arrays.append(DefCmd('Array', ArrayCreate(loop_iters)))
            new_array_inserts.append((spot+1, AssignCmd(str(-2-spot-len(new_arrays)), WireExp('array-store', ['i', Var(-1)]))))
            for ai,arg in enumerate(maki_prog.cmds[cur_index].rhs.args):
                if str(var) == str(arg):
                    maki_prog.cmds[cur_index].rhs.args = maki_prog.cmds[cur_index].rhs.args[:ai] + [WireExp('array-ref', [Var(for_start-cur_index-len(new_arrays)), WireSlice([which_iter])])] + maki_prog.cmds[cur_index].rhs.args[ai:]
            new_array_lines.add(spot)
        elif index < for_start:
            c.name = str(int(c.name) + loop_size*loop_iters - 1)

    def add_array_refs(c, argOp, argIndex, cur_index):
        if isinstance(c, (AssignCmd, DefCmd)):
            add_array_refs(c.rhs, None, None, cur_index)
            return
        if isinstance(c, (WireExp, ValExp)):
            for i,a in enumerate(c.args):
                add_array_refs(a, c.op, i, cur_index)
            return
        if isinstance(c, (Wire, Var)):
            if (argOp == 'array-ref' and argIndex == 0):
                fix_var(c.name, cur_index, c)
            elif argOp == 's' and argIndex == 0:
                fix_var(c.name, cur_index, c)
            elif argOp == 's' and argIndex and argIndex > 0:
                fix_var(c.name, cur_index, c)
            elif argOp in ['a+','a-','a*','a/','a%']:
                fix_var(c.name, cur_index, c)
            else:
                fix_var(c.name, cur_index, c)
            return
        if isinstance(c, WireSlice):
            # if c_next.vexps[0] != c.vexps[0]:
            #     c.vexps[0] = for_cmd.index
            for i, h in enumerate(c.vexps):
                add_array_refs(h, 's', None, cur_index)
            return
        if isinstance(c, ForCmd):
            for i, b in enumerate(c.body.cmds):
                add_array_refs(b, None, None, cur_index)
            return
        return

    for i in range(for_start + 1, len(maki_prog.cmds)):
        add_array_refs(maki_prog.cmds[i], None, None, i)
    
    for c in new_arrays:
        insert_cmd(maki_prog, for_start, c)

    for i, c in new_array_inserts:
        insert_cmd(for_cmd.body, i, c)

def debruijn_to_reg(db_prog):

    def adjust(dbi, cur_index, in_for):
        if abs(dbi) <= in_for:
            return '{}.{}'.format(cur_index - in_for - 1, in_for + dbi)
        return dbi + cur_index

    def renameVarUses(c, argOp, argIndex, cur_index, in_for):
        if isinstance(c, (AssignCmd, DefCmd)):
            renameVarUses(c.rhs, None, None, cur_index, in_for)
            return
        if isinstance(c, (WireExp, ValExp)):
            for i,a in enumerate(c.args):
                renameVarUses(a, c.op, i, cur_index, in_for)
            return
        if isinstance(c, (Wire, Var)):
            if (argOp == 'array-ref' and argIndex == 0):
                c.name = '{}'.format(adjust(int(c.name), cur_index, in_for))
            elif argOp == 's' and argIndex == 0:
                c.name = '{}'.format(adjust(int(c.name), cur_index, in_for))
            elif argOp == 's' and argIndex and argIndex > 0:
                c.name = '(& {})'.format(adjust(int(c.name), cur_index, in_for))
            elif argOp in ['a+','a-','a*','a/','a%']:
                c.name = '(& {})'.format(adjust(int(c.name), cur_index, in_for))
            else:
                c.name = '{}'.format(adjust(int(c.name), cur_index, in_for))
            return
        if isinstance(c, WireSlice):
            # if c_next.vexps[0] != c.vexps[0]:
            #     c.vexps[0] = for_cmd.index
            for i, h in enumerate(c.vexps):
                renameVarUses(h, 's', None, cur_index, in_for)
            return
        if isinstance(c, ForCmd):
            for i, b in enumerate(c.body.cmds):
                if isinstance(b, DefCmd):
                    b.lhs = '{}.{}'.format(cur_index, i)
                elif isinstance(b, AssignCmd):
                    b.lhs = int(b.lhs) + (i+1+cur_index)
                renameVarUses(b, None, None, i+1+cur_index, i)
            return
        return

    for i, cmd in enumerate(db_prog.cmds):
        cmd.lhs = str(i)
        renameVarUses(cmd, None, None, i, -1)
        

def insert_loop(maki_prog, start, size, num_iters):
    og_maki_prog = copy.deepcopy(maki_prog)
    block_cmds = maki_prog.cmds
    line_start = -1
    for i, cmd in enumerate(block_cmds):
        if str(start) == str(cmd.lhs):
            line_start = i
            break
    if line_start == -1:
        exit(-1)
    for_cmd = ForCmd('i', num_iters, Block(block_cmds[line_start:line_start+size]))
    to_add, maki_prog = fix_inner_deps(for_cmd, line_start, og_maki_prog)
    line_start = line_start + len(to_add)
    maki_prog = Block(maki_prog.cmds[:line_start] + [for_cmd] + maki_prog.cmds[line_start+size*num_iters:])
    fix_after_deps(maki_prog, for_cmd, line_start)
    debruijn_to_reg(maki_prog)
    return maki_prog