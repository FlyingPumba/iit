# %%
import transformer_lens

from iit.model_pairs.base_model_pair import HookName
import numpy as np
import torch as t
from transformer_lens.hook_points import HookedRootModule, HookPoint
from iit.utils.config import DEVICE
from iit.model_pairs.base_model_pair import HLNode, LLNode
from iit.utils.index import Ix
# from .utils import *

# %%

DEVICE = 'cuda' # TODO fix

IOI_NAMES = t.tensor([10, 20, 30]) # TODO

class DuplicateHead(t.nn.Module):
    def forward(self, tokens:t.Tensor):
        # Write the last previous position of any duplicated token (used at S2)
        positions = (tokens[..., None, :] == tokens[..., :, None]) # batch seq1 seq2
        positions = t.triu(positions, diagonal=1) # only consider positions before this one
        indices = positions.nonzero(as_tuple=True)
        ret = t.full_like(tokens, -1)
        ret[indices[0], indices[2]] = indices[1]
        return ret
    
class PreviousHead(t.nn.Module):
    def forward(self, tokens:t.Tensor):
        # copy token S1 to token S1+1 (used at S1+1)
        ret = t.full_like(tokens, -1)
        ret[..., 1:] = tokens[..., :-1]
        return ret

class InductionHead(t.nn.Module):
    """Induction heads omitted because they're redundant with duplicate heads in IOI"""
    

class SInhibitionHead(t.nn.Module):
    def forward(self, tokens: t.Tensor, duplicate: t.Tensor):
        """
        when duplicate is not -1, 
        output a flag to the name mover head to NOT copy this name
        flag is -1 if no duplicate name here, and name token for the name to inhibit
        """
        ret = tokens.clone()
        ret[duplicate == -1] = -1
        return ret
    
class NameMoverHead(t.nn.Module):
    def __init__(self, d_vocab:int=40, names=IOI_NAMES):
        super().__init__()
        self.d_vocab_out = d_vocab
        self.names = names

    def forward(self, tokens: t.Tensor, s_inhibition: t.Tensor):
        """
        increase logit of all names in the sentence, except those flagged by s_inhibition
        """
        batch, seq = tokens.shape
        logits = t.zeros((batch, seq, self.d_vocab_out)).to(DEVICE) # batch seq d_vocab
        # we want every name to increase its corresponding logit after it appears
        name_mask = tokens.eq(self.names[None, :, None]).any(dim=1)
        
        batch_indices, seq_indices = t.meshgrid(t.arange(batch), t.arange(seq), indexing='ij')
        logits[batch_indices, seq_indices, tokens] = 10 * name_mask.float()
        # now decrease the logit of the names that are inhibited
        logits[batch_indices, seq_indices, s_inhibition] += -15 * s_inhibition.ne(-1).float()
        logits = t.cumsum(logits, dim=1)
        return logits
    
# since 0, 3 contains 20, we write
# a 1 to position 0, 3, 20 of logits
        
# %%
        
class IOI_HL(HookedRootModule):
    """
    Components:
    - Duplicate token heads: write the previous position of any duplicated token
    - Previous token heads: copy token S1 to token S1+1
    - Induction heads (omitted): Attend to position written by duplicate token heads
    - S-inhibition heads: Inhibit attention of Name Mover Heads to S1 and S2 tokens
    - Name mover heads: Copy all previous names in the sentence
    """
    def __init__(self, d_vocab, names=IOI_NAMES):
        super().__init__()
        self.duplicate_head = DuplicateHead()
        self.hook_duplicate = HookPoint()
        self.previous_head = PreviousHead()
        self.hook_previous = HookPoint()
        self.s_inhibition_head = SInhibitionHead()
        self.hook_s_inhibition = HookPoint()
        self.name_mover_head = NameMoverHead(d_vocab, names)
        self.hook_name_mover = HookPoint()
        self.setup()

    # def get_idx_to_intermediate(self, name: HookName):
    #     """
    #     Returns a function that takes in a list of intermediate variables and returns the index of the one to use.
    #     """
    #     if name == 'hook_duplicate':
    #         return lambda intermediate_vars: intermediate_vars[:, 0]
    #     elif name == 'hook_previous':
    #         return lambda intermediate_vars: intermediate_vars[:, 1]
    #     elif name == 'hook_induction':
    #         return lambda intermediate_vars: intermediate_vars[:, 2]
    #     elif name == 'hook_s_inhibition':
    #         return lambda intermediate_vars: intermediate_vars[:, 3]
    #     elif name == 'hook_name_mover':
    #         return lambda intermediate_vars: intermediate_vars[:, 4]
    #     else:
    #         raise NotImplementedError(name)

    def forward(self, args, verbose=False):
        show = print if verbose else lambda *args, **kwargs: None
        input, label, _intermediate_data = args
        batched = True
        if len(input.shape) == 1:
            batched = False
            input = input[None, ...]
        # print([a.shape for a in args])
        # duplicate, previous, induction, s_inhibition, name_mover = [intermediate_data[:, i] for i in range(5)]
        # print(f"intermediate_data is a {type(intermediate_data)}; duplicate is a {type(duplicate)}")
        duplicate = self.duplicate_head(input)
        duplicate = self.hook_duplicate(duplicate)
        show(f"duplicate: {duplicate}")
        previous = self.previous_head(input)
        previous = self.hook_previous(previous)
        show(f"previous: {previous}")
        s_inhibition = self.s_inhibition_head(input, duplicate)
        s_inhibition = self.hook_s_inhibition(s_inhibition)
        show(f"s_inhibition: {s_inhibition}")
        out = self.name_mover_head(input, s_inhibition)
        out = self.hook_name_mover(out)
        if not batched:
            out = out[0]
        return out
# %%
