# Copyright 2019-2021 ETH Zurich and the DaCe authors. All rights reserved.
""" Moves a loop around a map into the map """

import copy
import dace
import dace.transformation.helpers as helpers
import networkx as nx
from dace.codegen import control_flow as cf
from dace.sdfg.scope import ScopeTree
from dace import data as dt, Memlet, nodes, sdfg as sd, subsets as sbs, symbolic, symbol
from dace.properties import CodeBlock
from dace.sdfg import graph, nodes, propagation, utils as sdutil
from dace.transformation import transformation
from dace.transformation.interstate.loop_detection import (DetectLoop, find_for_loop)
from sympy import diff
from typing import List, Set, Tuple


def fold(memlet_subset_ranges, itervar, lower, upper):
    return [(r[0].replace(symbol(itervar), lower), r[1].replace(symbol(itervar), upper), r[2])
            for r in memlet_subset_ranges]


def offset(memlet_subset_ranges, value):
    return (memlet_subset_ranges[0] + value, memlet_subset_ranges[1] + value, memlet_subset_ranges[2])


class MoveLoopIntoMap(DetectLoop, transformation.MultiStateTransformation):
    """
    Moves a loop around a map into the map
    """

    def can_be_applied(self, graph, expr_index, sdfg, permissive=False):
        # Is this even a loop
        if not super().can_be_applied(graph, expr_index, sdfg, permissive):
            return False

        # Obtain loop information
        guard: sd.SDFGState = self.loop_guard
        body: sd.SDFGState = self.loop_begin
        after: sd.SDFGState = self.exit_state

        # Obtain iteration variable, range, and stride
        loop_info = find_for_loop(sdfg, guard, body)
        if not loop_info:
            return False
        itervar, (start, end, step), (_, body_end) = loop_info

        if step not in [-1, 1]:
            return False

        # Body must contain a single state
        if body != body_end:
            return False

        # Body must have only a single connected component
        # NOTE: This is a strict check that can be potentially relaxed.
        # If only one connected component includes a Map and the others do not create RW dependencies, then we could
        # proceed with the transformation. However, that would be a case of an SDFG with redundant computation/copying,
        # which is unlikely after simplification transformations. Alternatively, we could try to apply the
        # transformation to each component separately, but this would require a lot more checks.
        if len(list(nx.weakly_connected_components(body._nx))) > 1:
            return False

        # Check if body contains exactly one map
        maps = [node for node in body.nodes() if isinstance(node, nodes.MapEntry)]
        if len(maps) != 1:
            return False

        map_entry = maps[0]
        map_exit = body.exit_node(map_entry)
        subgraph = body.scope_subgraph(map_entry)
        read_set, write_set = body.read_and_write_sets()

        # Check for iteration variable in map and data descriptors
        if str(itervar) in map_entry.free_symbols:
            return False
        for arr in (read_set | write_set):
            if str(itervar) in set(map(str, sdfg.arrays[arr].free_symbols)):
                return False

        # Check that everything else outside the Map is independent of the loop's itervar
        for e in body.edges():
            if e.src in subgraph.nodes() or e.dst in subgraph.nodes():
                continue
            if e.dst is map_entry and isinstance(e.src, nodes.AccessNode):
                continue
            if e.src is map_exit and isinstance(e.dst, nodes.AccessNode):
                continue
            if str(itervar) in e.data.free_symbols:
                return False
            if isinstance(e.dst, nodes.AccessNode) and e.dst.data in read_set:
                # NOTE: This is strict check that can be potentially relaxed.
                # If some data written indirectly by the Map (i.e., it is not an immediate output of the MapExit) is
                # also read, then abort. In practice, we could follow the edges and with subset compositions figure out
                # if there is a RW dependency on the loop variable. However, in such complicated cases, it is far more
                # likely that the simplification redundant array/copying transformations trigger first. If they don't,
                # this is a good hint that there is a RW dependency.
                if nx.has_path(body._nx, map_exit, e.dst):
                    return False
        for n in body.nodes():
            if n in subgraph.nodes():
                continue
            if str(itervar) in n.free_symbols:
                return False

        def test_subset_dependency(subset: sbs.Subset, mparams: Set[int]) -> Tuple[bool, List[int]]:
            dims = []
            for i, r in enumerate(subset):
                if not isinstance(r, (list, tuple)):
                    r = [r]
                fsymbols = set()
                for token in r:
                    if symbolic.issymbolic(token):
                        fsymbols = fsymbols.union({str(s) for s in token.free_symbols})
                if itervar in fsymbols:
                    if fsymbols.intersection(mparams):
                        return (False, [])
                    else:
                        # Strong checks
                        if not permissive:
                            # Only indices allowed
                            if len(r) > 1 and r[0] != r[1]:
                                return (False, [])
                            derivative = diff(r[0])
                            # Index function must be injective
                            if not (((derivative > 0) == True) or ((derivative < 0) == True)):
                                return (False, [])
                        dims.append(i)
            return (True, dims)

        # Check that Map memlets depend on itervar in a consistent manner
        # a. A container must either not depend at all on itervar, or depend on it always in the same dimensions.
        # b. Abort when a dimension depends on both the itervar and a Map parameter.
        mparams = set(map_entry.map.params)
        data_dependency = dict()
        for e in body.edges():
            if e.src in subgraph.nodes() and e.dst in subgraph.nodes():
                if itervar in e.data.free_symbols:
                    e.data.try_initialize(sdfg, subgraph, e)
                    for i, subset in enumerate((e.data.src_subset, e.data.dst_subset)):
                        if subset:
                            if i == 0:
                                access = body.memlet_path(e)[0].src
                            else:
                                access = body.memlet_path(e)[-1].dst
                            passed, dims = test_subset_dependency(subset, mparams)
                            if not passed:
                                return False
                            if dims:
                                if access.data in data_dependency:
                                    if data_dependency[access.data] != dims:
                                        return False
                                else:
                                    data_dependency[access.data] = dims

        return True

    def apply(self, _, sdfg: sd.SDFG):
        # Obtain loop information
        guard: sd.SDFGState = self.loop_guard
        body: sd.SDFGState = self.loop_begin

        # Obtain iteration variable, range, and stride
        itervar, (start, end, step), _ = find_for_loop(sdfg, guard, body)

        forward_loop = step > 0

        for node in body.nodes():
            if isinstance(node, nodes.MapEntry):
                map_entry = node
            if isinstance(node, nodes.MapExit):
                map_exit = node

        # nest map's content in sdfg
        map_subgraph = body.scope_subgraph(map_entry, include_entry=False, include_exit=False)
        nsdfg = helpers.nest_state_subgraph(sdfg, body, map_subgraph, full_data=True)

        # replicate loop in nested sdfg
        new_before, new_guard, new_after = nsdfg.sdfg.add_loop(
            before_state=None,
            loop_state=nsdfg.sdfg.nodes()[0],
            loop_end_state=None,
            after_state=None,
            loop_var=itervar,
            initialize_expr=f'{start}',
            condition_expr=f'{itervar} <= {end}' if forward_loop else f'{itervar} >= {end}',
            increment_expr=f'{itervar} + {step}' if forward_loop else f'{itervar} - {abs(step)}')

        # remove outer loop
        before_guard_edge = nsdfg.sdfg.edges_between(new_before, new_guard)[0]
        for e in nsdfg.sdfg.out_edges(new_guard):
            if e.dst is new_after:
                guard_after_edge = e
            else:
                guard_body_edge = e

        for body_inedge in sdfg.in_edges(body):
            if body_inedge.src is guard:
                guard_body_edge.data.assignments.update(body_inedge.data.assignments)
            sdfg.remove_edge(body_inedge)
        for body_outedge in sdfg.out_edges(body):
            sdfg.remove_edge(body_outedge)
        for guard_inedge in sdfg.in_edges(guard):
            before_guard_edge.data.assignments.update(guard_inedge.data.assignments)
            guard_inedge.data.assignments = {}
            sdfg.add_edge(guard_inedge.src, body, guard_inedge.data)
            sdfg.remove_edge(guard_inedge)
        for guard_outedge in sdfg.out_edges(guard):
            if guard_outedge.dst is body:
                guard_body_edge.data.assignments.update(guard_outedge.data.assignments)
            else:
                guard_after_edge.data.assignments.update(guard_outedge.data.assignments)
            guard_outedge.data.condition = CodeBlock("1")
            sdfg.add_edge(body, guard_outedge.dst, guard_outedge.data)
            sdfg.remove_edge(guard_outedge)
        sdfg.remove_node(guard)
        if itervar in nsdfg.symbol_mapping:
            del nsdfg.symbol_mapping[itervar]
        if itervar in sdfg.symbols:
            del sdfg.symbols[itervar]

        # Add missing data/symbols
        for s in nsdfg.sdfg.free_symbols:
            if s in nsdfg.symbol_mapping:
                continue
            if s in sdfg.symbols:
                nsdfg.symbol_mapping[s] = s
            elif s in sdfg.arrays:
                desc = sdfg.arrays[s]
                access = body.add_access(s)
                conn = nsdfg.sdfg.add_datadesc(s, copy.deepcopy(desc))
                nsdfg.sdfg.arrays[s].transient = False
                nsdfg.add_in_connector(conn)
                body.add_memlet_path(access, map_entry, nsdfg, memlet=Memlet.from_array(s, desc), dst_conn=conn)
            else:
                raise NotImplementedError(f"Free symbol {s} is neither a symbol nor data.")
        to_delete = set()
        for s in nsdfg.symbol_mapping:
            if s not in nsdfg.sdfg.free_symbols:
                to_delete.add(s)
        for s in to_delete:
            del nsdfg.symbol_mapping[s]

        # propagate scope for correct volumes
        scope_tree = ScopeTree(map_entry, map_exit)
        scope_tree.parent = ScopeTree(None, None)
        # The first execution helps remove apperances of symbols
        # that are now defined only in the nested SDFG in memlets.
        propagation.propagate_memlets_scope(sdfg, body, scope_tree)

        for s in to_delete:
            if helpers.is_symbol_unused(sdfg, s):
                sdfg.remove_symbol(s)

        from dace.transformation.interstate import RefineNestedAccess
        transformation = RefineNestedAccess()
        transformation.setup_match(sdfg, 0, sdfg.node_id(body), {RefineNestedAccess.nsdfg: body.node_id(nsdfg)}, 0)
        transformation.apply(body, sdfg)

        # Second propagation for refined accesses.
        propagation.propagate_memlets_scope(sdfg, body, scope_tree)


class MoveMapIntoLoop(transformation.SingleStateTransformation):
    """
    Moves a map around a loop into the loop
    """

    map_entry = transformation.PatternNode(nodes.EntryNode)
    nested_sdfg = transformation.PatternNode(nodes.NestedSDFG)
    map_exit = transformation.PatternNode(nodes.ExitNode)

    @staticmethod
    def annotates_memlets():
        return False

    @classmethod
    def expressions(cls):
        return [sdutil.node_path_graph(cls.map_entry, cls.nested_sdfg, cls.map_exit)]

    def can_be_applied(self, graph, expr_index, sdfg, permissive=False):

        # If the body a loop?
        nsdfg = self.nested_sdfg.sdfg
        components = helpers.find_sdfg_control_flow(nsdfg)
        # Body must contain a single control-flow component
        if len(components) != 1:
            return False
        cf_node: cf.ControlFlow
        _, cf_node = list(components.values())[0]
        # Component must be ForScope
        if not isinstance(cf_node, cf.ForScope):
            return False

        mparams = set(self.map_entry.map.params)

        # Obtain loop information
        guard: sd.SDFGState = cf_node.guard
        body: sd.SDFGState = cf_node.body.first_state

        # Obtain iteration variable, range, and stride
        loop_info = find_for_loop(nsdfg, guard, body)
        if not loop_info:
            return False
        itervar, (start, end, step), (_, body_end) = loop_info
        dependent_symbols = set(mparams)
        for k, v in self.nested_sdfg.symbol_mapping.items():
            try:
                fsymbols = v.free_symbols
            except AttributeError:
                fsymbols = set()
            if any(str(f) in dependent_symbols for f in fsymbols):
                dependent_symbols.add(k)
        for s in (start, end, step):
            if any(str(s) in dependent_symbols for s in s.free_symbols):
                return False

        # Collect read and writes from states
        read_set: Set[str] = set()
        write_set: Set[str] = set()
        for state in nsdfg.states():
            rset, wset = state.read_and_write_sets()
            read_set |= rset
            write_set |= wset

        # Check for map parameters in data descriptors
        for arr in (read_set | write_set):
            if any(p in set(map(str, nsdfg.arrays[arr].free_symbols)) for p in mparams):
                return False

        def test_subset_dependency(subset: sbs.Subset) -> Tuple[bool, List[int]]:
            dims = []
            for i, r in enumerate(subset):
                if not isinstance(r, (list, tuple)):
                    r = [r]
                fsymbols = set()
                for token in r:
                    if symbolic.issymbolic(token):
                        fsymbols = fsymbols.union({str(s) for s in token.free_symbols})
                if itervar in fsymbols:
                    if fsymbols.intersection(mparams):
                        return (False, [])
                    else:
                        # Strong checks
                        if not permissive:
                            # Only indices allowed
                            if len(r) > 1 and r[0] != r[1]:
                                return (False, [])
                            derivative = diff(r[0])
                            # Index function must be injective
                            if not (((derivative > 0) == True) or ((derivative < 0) == True)):
                                return (False, [])
                        dims.append(i)
            return (True, dims)

        # Check that NestedSDFG memlets depend on map params in a consistent manner
        # a. A container must either not depend at all on itervar, or depend on it always in the same dimensions.
        # b. Abort when a dimension depends on both the itervar and a Map parameter.
        data_dependency = dict()
        for state in nsdfg.states():
            for e in state.edges():
                if any(p in e.data.free_symbols for p in mparams):
                    e.data.try_initialize(nsdfg, state, e)
                    for i, subset in enumerate((e.data.src_subset, e.data.dst_subset)):
                        if subset:
                            if i == 0:
                                access = state.memlet_path(e)[0].src
                            else:
                                access = state.memlet_path(e)[-1].dst
                            passed, dims = test_subset_dependency(subset)
                            if not passed:
                                return False
                            if dims:
                                if access.data in data_dependency:
                                    if data_dependency[access.data] != dims:
                                        return False
                                else:
                                    data_dependency[access.data] = dims

        return True

    def apply(self, graph: sd.SDFGState, sdfg: sd.SDFG):

        nsdfg = self.nested_sdfg.sdfg
        components = helpers.find_sdfg_control_flow(nsdfg)
        cf_node: cf.ForScope
        _, cf_node = list(components.values())[0]
        mparams = set(self.map_entry.map.params)

        # Obtain loop information
        guard: sd.SDFGState = cf_node.guard
        body: sd.SDFGState = cf_node.body.first_state

        # Obtain iteration variable, range, and stride
        loop_info = find_for_loop(nsdfg, guard, body)
        if not loop_info:
            return False
        itervar, (start, end, step), (_, body_end) = loop_info

        forward_loop = step > 0

        # nest map's content in sdfg
        map_subgraph = graph.scope_subgraph(self.map_entry, include_entry=True, include_exit=True)
        new_nsdfg = helpers.nest_state_subgraph(sdfg, graph, map_subgraph, full_data=True)

        # replicate loop in nested sdfg
        new_before, new_guard, new_after = new_nsdfg.sdfg.add_loop(
            before_state=None,
            loop_state=new_nsdfg.sdfg.nodes()[0],
            loop_end_state=None,
            after_state=None,
            loop_var=itervar,
            initialize_expr=f'{start}',
            condition_expr=f'{itervar} <= {end}' if forward_loop else f'{itervar} >= {end}',
            increment_expr=f'{itervar} + {step}' if forward_loop else f'{itervar} - {abs(step)}')
        new_nsdfg.sdfg.start_state = new_nsdfg.sdfg.node_id(new_before)

        # remove inner loop
        for e in nsdfg.in_edges(guard):
            if e.src not in (body, body_end):
                nsdfg.remove_node(e.src)
                # nsdfg.remove_edge(e)
        for e in nsdfg.out_edges(guard):
            if e.dst not in (body, body_end):
                nsdfg.remove_node(e.dst)
                # nsdfg.remove_edge(e)
        nsdfg.remove_node(guard)

        # Add itervar to nested-nested SDFG
        if itervar in nsdfg.symbols:
            nsdfg.parent_nsdfg_node.symbol_mapping[itervar] = dace.symbol(itervar, nsdfg.symbols[itervar])
        else:
            nsdfg.add_symbol(itervar, dace.int32)
            nsdfg.parent_nsdfg_node.symbol_mapping[itervar] = dace.symbol(itervar, dace.int32)

        from dace.transformation.interstate import RefineNestedAccess
        propagation.propagate_states(new_nsdfg.sdfg)
        propagation.propagate_memlets_state(new_nsdfg.sdfg, nsdfg.parent)
        nsdfg.apply_transformations_repeated(RefineNestedAccess)
        propagation.propagate_memlets_state(sdfg, graph)


class MoveMapIntoIf(transformation.SingleStateTransformation):
    """
    Moves a Map around an IfScope into the IfScope.
    """

    map_entry = transformation.PatternNode(nodes.EntryNode)
    nested_sdfg = transformation.PatternNode(nodes.NestedSDFG)
    map_exit = transformation.PatternNode(nodes.ExitNode)

    @staticmethod
    def annotates_memlets():
        return False

    @classmethod
    def expressions(cls):
        return [sdutil.node_path_graph(cls.map_entry, cls.nested_sdfg, cls.map_exit)]

    def can_be_applied(self, graph, expr_index, sdfg, permissive=False):

        # Is the body an IfScope?
        nsdfg = self.nested_sdfg.sdfg
        components = helpers.find_sdfg_control_flow(nsdfg)
        # Body must contain a single control-flow component
        if len(components) != 1:
            return False
        cf_node: cf.ControlFlow
        _, cf_node = list(components.values())[0]
        # Component must be IfScope
        if not isinstance(cf_node, cf.IfScope):
            return False

        mparams = set(self.map_entry.map.params)

        # Check basic structure of the IfScope.
        # The guard state must be empty
        if_guard: dace.SDFGState = cf_node.branch_state
        if len(if_guard.nodes()) != 0:
            return False
        # There must be a single sink state, the if-exit state.
        sink_states = nsdfg.sink_nodes()
        if len(sink_states) != 1:
            return False
        # The exit state must be empty.
        if_exit: dace.SDFGState = sink_states[0]
        if len(if_exit.nodes()) != 0:
            return False
        # We do not handle "orelse" yet.
        if cf_node.orelse is not None:
            return False
        # The condition must not depend on the Map parameters.
        condition = cf_node.condition
        symbols_to_check = set(mparams)
        for k, v in self.nested_sdfg.symbol_mapping.items():
            try:
                if symbolic.issymbolic(v):
                    fsymbols = v.free_symbols
                else:
                    fsymbols = symbolic.pystr_to_symbolic(v).free_symbols
            except AttributeError:
                fsymbols = set()
            if any(str(f) in symbols_to_check for f in fsymbols):
                symbols_to_check.add(k)
        if any(str(s) in symbols_to_check for s in condition.get_free_symbols()):
            return False

        # Collect read and writes from states
        read_set: Set[str] = set()
        write_set: Set[str] = set()
        for state in nsdfg.states():
            rset, wset = state.read_and_write_sets()
            read_set |= rset
            write_set |= wset

        # Check for map parameters in data descriptors
        for arr in (read_set | write_set):
            if any(p in set(map(str, nsdfg.arrays[arr].free_symbols)) for p in mparams):
                return False

        def test_subset_dependency(subset: sbs.Subset) -> Tuple[bool, List[int]]:
            dims = []
            for i, r in enumerate(subset):
                if not isinstance(r, (list, tuple)):
                    r = [r]
                fsymbols = set()
                for token in r:
                    if symbolic.issymbolic(token):
                        fsymbols = fsymbols.union({str(s) for s in token.free_symbols})
                # NOTE: IfScopes don't have an iteration variable. Does this mean that we can ignore everything below?
                # if itervar in fsymbols:
                #     if fsymbols.intersection(mparams):
                #         return (False, [])
                #     else:
                #         # Strong checks
                #         if not permissive:
                #             # Only indices allowed
                #             if len(r) > 1 and r[0] != r[1]:
                #                 return (False, [])
                #             derivative = diff(r[0])
                #             # Index function must be injective
                #             if not (((derivative > 0) == True) or ((derivative < 0) == True)):
                #                 return (False, [])
                #         dims.append(i)
            return (True, dims)

        # Check that NestedSDFG memlets depend on map params in a consistent manner
        # a. A container must either not depend at all on itervar, or depend on it always in the same dimensions.
        # b. Abort when a dimension depends on both the itervar and a Map parameter.
        data_dependency = dict()
        for state in nsdfg.states():
            for e in state.edges():
                if any(p in e.data.free_symbols for p in mparams):
                    e.data.try_initialize(nsdfg, state, e)
                    for i, subset in enumerate((e.data.src_subset, e.data.dst_subset)):
                        if subset:
                            if i == 0:
                                access = state.memlet_path(e)[0].src
                            else:
                                access = state.memlet_path(e)[-1].dst
                            passed, dims = test_subset_dependency(subset)
                            if not passed:
                                return False
                            if dims:
                                if access.data in data_dependency:
                                    if data_dependency[access.data] != dims:
                                        return False
                                else:
                                    data_dependency[access.data] = dims

        return True

    def apply(self, graph: sd.SDFGState, sdfg: sd.SDFG):

        nsdfg = self.nested_sdfg.sdfg
        components = helpers.find_sdfg_control_flow(nsdfg)
        cf_node: cf.ControlFlow
        _, cf_node = list(components.values())[0]
        mparams = set(self.map_entry.map.params)

        if_guard: dace.SDFGState = cf_node.branch_state
        ipostdom = sdutil.postdominators(nsdfg)
        if_exit: dace.SDFGState = ipostdom[if_guard]
        condition = cf_node.condition
        inv_condition = nsdfg.edges_between(if_guard, if_exit)[0].data.condition

        # remove IfScope.
        nsdfg.remove_nodes_from([if_guard, if_exit])

        # nest map's content in sdfg
        map_subgraph = graph.scope_subgraph(self.map_entry, include_entry=True, include_exit=True)
        new_nsdfg = helpers.nest_state_subgraph(sdfg, graph, map_subgraph, full_data=True)

        # replicate IfScope in nested sdfg

        body = new_nsdfg.sdfg.nodes()[0]
        if_guard = new_nsdfg.sdfg.add_state('if_guard')
        if_exit = new_nsdfg.sdfg.add_state('if_exit')
        new_nsdfg.sdfg.add_edge(if_guard, body, dace.InterstateEdge(condition=condition))
        new_nsdfg.sdfg.add_edge(if_guard, if_exit, dace.InterstateEdge(condition=inv_condition))
        new_nsdfg.sdfg.add_edge(body, if_exit, dace.InterstateEdge())

        from dace.transformation.interstate import RefineNestedAccess
        propagation.propagate_states(new_nsdfg.sdfg)
        propagation.propagate_memlets_state(new_nsdfg.sdfg, nsdfg.parent)
        nsdfg.apply_transformations_repeated(RefineNestedAccess)
        propagation.propagate_memlets_state(sdfg, graph)
