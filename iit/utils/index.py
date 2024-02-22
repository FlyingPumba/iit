# %%
from typing import Optional, List, Iterable

# %%

"""copied from https://github.com/ArthurConmy/Automatic-Circuit-Discovery/blob/14c75e9898eda70a8e0997390077af1ec2543258/acdc/TLACDCEdge.py"""


class TorchIndex:
    """There is not a clean bijection between things we
    want in the computational graph, and things that are hooked
    (e.g hook_result covers all heads in a layer)

    `TorchIndex`s are essentially indices that say which part of the tensor is being affected.

    EXAMPLES: Initialise [:, :, 3] with TorchIndex([None, None, 3]) and [:] with TorchIndex([None])

    Also we want to be able to call e.g `my_dictionary[my_torch_index]` hence the hashable tuple stuff

    Note: ideally this would be integrated with transformer_lens.utils.Slice in future; they are accomplishing similar but different things
    """

    def __init__(
        self,
        list_of_things_in_tuple: Iterable,
    ):
        # check correct types
        for arg in list_of_things_in_tuple:
            if type(arg) in [type(None), int, slice]:
                continue
            else:
                assert isinstance(arg, list)
                assert all([type(x) == int for x in arg])

        # make an object that can be indexed into a tensor
        self.as_index = tuple(
            [slice(None) if x is None else x for x in list_of_things_in_tuple]
        )

        # make an object that can be hashed (so used as a dictionary key)
        # compatibility with python <3.12 where slices are not hashable
        self.hashable_tuple = tuple(
            (
                i.__reduce__() if isinstance(i, slice) else i
                for i in list_of_things_in_tuple
            )
        )

    def __hash__(self):
        return hash(self.hashable_tuple)

    def __eq__(self, other):
        return self.hashable_tuple == other.hashable_tuple

    def __repr__(self) -> str:
        ret = "["
        for idx, x in enumerate(self.hashable_tuple):
            if idx > 0:
                ret += ", "
            if x is None:
                ret += ":"
            elif type(x) == int:
                ret += str(x)
            elif x[0] == slice:
                x = slice(*x[1])
                ret += (
                    (str(x.start) if x.start is not None else "")
                    + ":"
                    + (str(x.stop) if x.stop is not None else "")
                )
                assert x.step is None, "Step is not supported"
            else:
                raise NotImplementedError(x)
        ret += "]"
        return ret

    def graphviz_index(self, use_actual_colon=True) -> str:
        return self.__repr__(use_actual_colon=use_actual_colon)

    def intersects(self, other) -> bool:
        if len(self.as_index) != len(other.as_index):
            raise ValueError("Cannot compare indices of different lengths")
        for i, (a, b) in enumerate(zip(self.as_index, other.as_index)):
            if a == slice(None) or b == slice(None):
                continue
            if type(a) == int and type(b) == int:
                if a != b:
                    return False
            elif type(a) == slice and type(b) == slice:
                if a.start is None and b.start is None:
                    start = 0
                else:
                    start = max(a.start, b.start)
                if a.stop is None and b.stop is None:
                    stop = float("inf")
                else:
                    stop = min(a.stop, b.stop)
                if start >= stop:
                    return False
            else:
                # either a or b is a slice, the other is an int
                tu = b if type(a) == int else a
                ntu = a if type(a) == int else b
                tu_start = tu.start if tu.start is not None else 0
                tu_stop = tu.stop if tu.stop is not None else float("inf")
                if tu_start <= ntu < tu_stop:
                    continue
                else:
                    return False
        return True


class Index:
    """A class purely for syntactic sugar, that returns the index it's indexed with"""

    def __getitem__(self, index):
        return TorchIndex(index)


Ix = Index()
