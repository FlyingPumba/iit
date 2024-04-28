import iit.utils.index as index
import iit.model_pairs as mp
from transformer_lens import HookedTransformer
import torch as t

LLParamNode = mp.LLNode


def get_hook_suffix(corr: dict[mp.HLNode, set[mp.LLNode]]) -> str:
    suffixes = {}
    for hl_node, ll_nodes in corr.items():
        for ll_node in ll_nodes:
            # add everything after 'blocks.<layer>.' to the set
            suffix = ll_node.name.split(".")[2:]
            suffix = ".".join(suffix)
            if "attn" in ll_node.name:
                if "attn" in suffixes and suffixes["attn"] != suffix:
                    raise ValueError(
                        f"Multiple attn suffixes found: {suffixes['attn']} and {suffix}, multiple attn hook locations are not supported yet."
                    )
                suffixes["attn"] = suffix
            elif "mlp" in ll_node.name:
                if "mlp" in suffixes and suffixes["mlp"] != suffix:
                    raise ValueError(
                        f"Multiple mlp suffixes found: {suffixes['mlp']} and {suffix}, multiple mlp hook locations are not supported yet."
                    )
                suffixes["mlp"] = suffix
            else:
                raise ValueError(f"Unknown node type {ll_node.name}")

    return suffixes


def get_all_nodes(
    model: HookedTransformer,
    suffixes: dict[str, str] = {
        "attn": "attn.hook_result",
        "mlp": "mlp.hook_post",
    },
) -> list[mp.LLNode]:
    nodes = []
    n_heads = model.cfg.n_heads
    n_layers = model.cfg.n_layers
    for layer in range(n_layers):
        hook_point = f"blocks.{layer}.{suffixes['attn']}"
        for head in range(n_heads):
            head_node = mp.LLNode(hook_point, index.Ix[:, :, head, :])
            nodes.append(head_node)
        hook_point = f"blocks.{layer}.{suffixes['mlp']}"
        nodes.append(mp.LLNode(hook_point, index.Ix[[None]]))
    return nodes


def get_nodes_in_circuit(hl_ll_corr) -> list[mp.LLNode]:
    nodes_in_circuit = set()
    for hl_node, ll_nodes in hl_ll_corr.items():
        nodes_in_circuit.update(ll_nodes)
    return list(nodes_in_circuit)


def nodes_intersect(a: mp.LLNode, b: mp.LLNode) -> bool:
    # return true if there is any intersection
    if a.name != b.name:
        return False
    return a.index.intersects(b.index)


def get_nodes_not_in_circuit(
    ll_model: HookedTransformer,
    hl_ll_corr,
    suffixes={
        "attn": "attn.hook_result",
        "mlp": "mlp.hook_post",
    },
) -> list[mp.LLNode]:
    all_nodes = get_all_nodes(ll_model, suffixes)
    nodes_in_circuit = get_nodes_in_circuit(hl_ll_corr)
    nodes_not_in_circuit = []
    for node in all_nodes:
        if not any(nodes_intersect(node, c) for c in nodes_in_circuit):
            nodes_not_in_circuit.append(node)
    return nodes_not_in_circuit


def get_post_nodes_not_in_circuit(
    ll_model: HookedTransformer,
    hl_ll_corr,
    suffixes={
        "attn": "attn.hook_result",
        "mlp": "mlp.hook_post",
    },
) -> list[mp.LLNode]:
    print("WARNING: This doesn't work when switching individual heads on/off.")
    nodes_not_in_circuit = get_nodes_not_in_circuit(ll_model, hl_ll_corr)
    post_nodes_not_in_circuit = []
    for node in nodes_not_in_circuit:
        layer = int(node.name.split(".")[1])
        if "attn" in node.name and  "attn" in suffixes:
            post_hook_name = f"blocks.{layer}.{suffixes['attn']}"
        elif "mlp" in suffixes:
            post_hook_name = f"blocks.{layer}.{suffixes['mlp']}"
        append_node = True
        for pn in post_nodes_not_in_circuit:
            if pn.name == post_hook_name:
                append_node = False
                break
        if append_node:
            post_node = mp.LLNode(post_hook_name, index.Ix[[None]])
            post_nodes_not_in_circuit.append(post_node)
    return post_nodes_not_in_circuit


def _get_param_idx(
    name: str, param: t.nn.parameter.Parameter, node: mp.LLNode
) -> index.TorchIndex:
    param_type = name.split(".")[-1]
    node_idx = node.index
    none_ix = index.Ix[[None]]

    if node.subspace is not None:
        raise NotImplementedError("Subspaces are not supported")
    if node_idx == none_ix or param_type == "b_O":
        param_idx = none_ix
    elif param_type in ["W_Q", "W_K", "W_V"]:
        param_idx = index.TorchIndex(node_idx.as_index[:-1])
    elif param_type == "W_O":
        idx_tuple = list(node_idx.as_index[:-1])
        param_idx = index.TorchIndex([idx_tuple[0], idx_tuple[2], idx_tuple[1]])
    elif param_type in ["b_Q", "b_K", "b_V"]:
        idx_tuple = list(node_idx.as_index[:-1])
        param_idx = index.TorchIndex([slice(None), idx_tuple[2]])
    else:
        raise NotImplementedError(
            f"Param of type '{param_type}' is expected to have index {none_ix}, but got {node_idx}"
        )

    try:
        param[param_idx.as_index]
    except IndexError:
        raise IndexError(f"Index {param_idx} is out of bounds for param {name}")

    return param_idx


def get_activation_idx(node: LLParamNode) -> index.TorchIndex:
    param_type = node.name.split(".")[-1]
    idx_tuple = node.index.as_index
    if param_type in ["W_Q", "W_K", "W_V"]:
        return index.TorchIndex([slice(None), *idx_tuple])
    elif param_type in ["b_Q", "b_K", "b_V"]:
        return index.TorchIndex([slice(None), *idx_tuple, slice(None)])
    elif param_type == "W_O":
        return index.TorchIndex([idx_tuple[0], idx_tuple[2], idx_tuple[1], slice(None)])
    else:
        return index.Ix[[None]]


def get_params_in_circuit(
    hl_ll_corr: dict[str, set[mp.LLNode]], ll_model: HookedTransformer
) -> list[LLParamNode]:
    nodes_in_circuit = get_nodes_in_circuit(hl_ll_corr)
    params_in_circuit = []
    for name, param in ll_model.named_parameters():
        for node in nodes_in_circuit:
            node_name = ".".join(node.name.split(".")[:-1])
            param_name = ".".join(name.split(".")[:-1])
            if node_name == param_name:
                param_idx = _get_param_idx(name, param, node)
                params_in_circuit.append(LLParamNode(name, param_idx))
    return params_in_circuit


def get_all_params(ll_model: HookedTransformer) -> list[LLParamNode]:
    params = []
    for name, param in ll_model.named_parameters():
        param_type = name.split(".")[-1]
        if param_type in ["W_Q", "W_K", "W_V", "W_O", "b_Q", "b_K", "b_V"]:
            for head in range(ll_model.cfg.n_heads):
                idx = index.Ix[:, :, head, :]
                param_idx = _get_param_idx(name, param, LLParamNode(name, idx))
                params.append(LLParamNode(name, param_idx))
        else:
            param_idx = index.Ix[[None]]
            params.append(LLParamNode(name, param_idx))
    return params


def get_params_not_in_circuit(
    hl_ll_corr: dict[str, set[mp.LLNode]],
    ll_model: HookedTransformer,
    filter_out_embed: bool = True,
) -> list[LLParamNode]:
    nodes_in_circuit = get_nodes_in_circuit(hl_ll_corr)
    all_params = get_all_params(ll_model)
    params_not_in_circuit = []
    for param in all_params:
        if filter_out_embed and "embed" in param.name:
            continue
        if not any(nodes_intersect(param, c) for c in nodes_in_circuit):
            params_not_in_circuit.append(param)
    return params_not_in_circuit
