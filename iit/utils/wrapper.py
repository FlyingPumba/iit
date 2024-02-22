import torch as t
from torch import Tensor
from transformer_lens.hook_points import HookedRootModule, HookPoint


class HookedModuleWrapper(HookedRootModule):
    """
    Wraps any module, adding a hook after the output.
    """

    def __init__(
        self,
        mod: t.nn.Module,
        name="model",
        recursive=False,
        hook_self=True,
        top_level=True,
        hook_pre=False,
    ):
        super().__init__()
        self.mod = mod  # deepcopy(mod)
        self.hook_self = hook_self
        self.hook_pre = hook_pre
        if hook_pre:
            self.hook_pre = HookPoint()
            self.hook_pre.name = name + "pre"
        if hook_self:
            hook_point = HookPoint()
            hook_point.name = name
            self.hook_point = hook_point
        if recursive:
            self.wrap_hookpoints_recursively()
        self.setup()

    def wrap_hookpoints_recursively(self, verbose=False):
        show = lambda *args: print(*args) if verbose else None
        for key, submod in list(self.mod._modules.items()):
            if isinstance(submod, HookedModuleWrapper):
                show(f"SKIPPING {key}:{type(submod)}")
                continue
            if key in ["intermediate_value_head", "value_head"]:  # these return tuples
                show(f"SKIPPING {key}:{type(submod)}")
                continue
            if isinstance(submod, t.nn.ModuleList):
                show(f"INDIVIDUALLY WRAPPING {key}:{type(submod)}")
                for i, subsubmod in enumerate(submod):
                    new_submod = HookedModuleWrapper(
                        subsubmod, name=f"{key}.{i}", recursive=True, top_level=False
                    )
                    submod[i] = new_submod
                continue
            # print(f'wrapping {key}:{type(submod)}')
            new_submod = HookedModuleWrapper(
                submod, name=key, recursive=True, top_level=False
            )
            self.mod.__setattr__(key, new_submod)

    def forward(self, *args, **kwargs):
        if self.hook_pre:
            result = self.mod.forward(self.hook_pre(*args, **kwargs))
        else:
            result = self.mod.forward(*args, **kwargs)
        if not self.hook_self:
            return result
        assert isinstance(result, Tensor)
        return self.hook_point(result)


def get_hook_points(model: HookedRootModule):
    return [k for k in list(model.hook_dict.keys()) if "conv" in k]
