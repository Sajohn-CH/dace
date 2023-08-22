import dace


def test_remove_unused_scalar():
    sdfg = dace.SDFG('trivial_map')
    sdfg.add_scalar('A', dace.float64)
    sdfg.add_scalar('B', dace.float64)
    state = sdfg.add_state()

    # Nodes
    read = state.add_read('A')
    write = state.add_write('A')
    tasklet = state.add_tasklet('tasklet', {'a_in'}, {'a_out'}, 'a_out = a_in + 1')
    state.add_memlet_path(read, tasklet, memlet=dace.Memlet.simple('A', '0'), dst_conn='a_in')
    state.add_memlet_path(tasklet, write, memlet=dace.Memlet.simple('A', '0'), src_conn='a_out')
    sdfg.validate()

    sdfg.simplify()
    sdfg.validate()
    assert 'B' not in sdfg.arrays


def test_remove_unused_array():
    sdfg = dace.SDFG('trivial_map')
    sdfg.add_array('A', [5], dace.float64)
    sdfg.add_array('B', [5], dace.float64)
    state = sdfg.add_state()

    # Nodes
    read = state.add_read('A')
    write = state.add_write('A')
    tasklet = state.add_tasklet('tasklet', {'a_in'}, {'a_out'}, 'a_out = a_in + 1')
    state.add_memlet_path(read, tasklet, memlet=dace.Memlet.simple('A', '0'), dst_conn='a_in')
    state.add_memlet_path(tasklet, write, memlet=dace.Memlet.simple('A', '0'), src_conn='a_out')
    sdfg.validate()

    sdfg.simplify()
    sdfg.validate()
    assert 'B' not in sdfg.arrays


def main():
    test_remove_unused_scalar()
    test_remove_unused_array()


if __name__ == '__main__':
    main()
