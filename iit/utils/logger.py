import os
import torch
import numpy as np
import time
np.set_printoptions(threshold=np.inf)

class LoggingDict(dict):
    def __init__(self, *args, **kwargs):
        dirname = "logs"
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        self._log_filename = os.path.join(dirname, f"log_{time.strftime('%m-%d_%H-%M')}.log")
        
        super().__init__(*args, **kwargs)

    def compare(self, x, y):
        if isinstance(x, (torch.Tensor)):
            assert isinstance(y, (torch.Tensor)), "x and y are not the same type"
            return (x == y).all()
        elif isinstance(x, (np.ndarray)):
            assert isinstance(y, (np.ndarray)), "x and y are not the same type"
            return (x == y).all()
        elif isinstance(x, (list)):
            assert isinstance(y, (list)), "x and y are not the same type"
            return all(self.compare(x[i], y[i]) for i in range(len(x)))
        else:
            return x == y
    
    def convert_tensor_to_numpy(self, x):
        if isinstance(x, (torch.Tensor)):
            return x.cpu().detach().numpy()
        return x
    
    def __setitem__(self, key, value):
        if key not in self:
            with open(self._log_filename, "a") as f:
                f.write(f"{key}\n initial value: {value}\n")
        elif not self.compare(self[key], value):
            with open(self._log_filename, "a") as f:
                f.write(f"{key}\n changed from {self[key]} to {value}\n")
        super().__setitem__(key, value)


if __name__ == "__main__":
    logger = LoggingDict()
    logger["a"] = 1
    logger["b"] = 2
    logger["c"] = 3
    logger["a"] = 4
    filename = logger._log_filename
    file = open(logger._log_filename, "r")
    print(file.read())