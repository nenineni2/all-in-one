from typing import Callable, Self, Any
from contextlib import contextmanager


class LazyList:
    __functions: list[Callable[[], list]]
    __values: dict[int, Any] = {}
    __index = 0
    __caching = True

    def __init__(self: Self, fn: list[Callable]) -> None:
        self.__functions = fn

    def __getitem__(self: Self, item: int) -> Any:
        if type(item) is int:
            if self.__caching:
                if self.__values.get(item) is None:
                    self.__values[item] = self.__functions[item]()
                    return self.__values[item]
                else:
                    return self.__values[item]
            else:
                return self.__functions[item]()

    def __iter__(self):
        self.__index = 0
        return self

    def __next__(self):
        if self.__index < len(self.__functions):
            if self.__caching:
                if self.__values.get(self.__index) is None:
                    self.__values[self.__index] = self.__functions[self.__index]()
                    result = self.__values[self.__index]
                    self.__index += 1
                    return result
                else:
                    result = self.__values[self.__index]
                    self.__index += 1
                    return result
            else:
                self.__index += 1
                return self.__functions[self.__index - 1]()
        else:
            raise StopIteration

    def __aiter__(self):
        self.__index = 0
        return self

    async def __anext__(self):
        if self.__index < len(self.__functions):
            if self.__caching:
                if self.__values.get(self.__index) is None:
                    self.__values[self.__index] = self.__functions[self.__index]()
                    result = self.__values[self.__index]
                    self.__index += 1
                    return result
                else:
                    result = self.__values[self.__index]
                    self.__index += 1
                    return result
            else:
                self.__index += 1
                return self.__functions[self.__index - 1]()
        else:
            raise StopAsyncIteration

    def __delitem__(self, item: int):
        del self.__values[item]

    def __len__(self):
        return len(self.__functions)

    def __repr__(self) -> str:
        return str(self.__values)

    @contextmanager
    def prefetch(self, elements: int):
        result = []
        for idx, fn in enumerate(self.__functions[:elements]):
            if self.__caching:
                if self.__values.get(idx) is None:
                    self.__values[idx] = fn()
                    result.append(self.__values[idx])
                else:
                    result.append(self.__values[idx])
            else:
                result.append(fn())
        try:
            yield result
        finally:
            ...

    @contextmanager
    def no_cache(self):
        self.__caching = False
        try:
            yield self.__values
        finally:
            self.__caching = True

    def clear_cache(self):
        self.__values = {}

    @property
    def computed_nodes(self):
        return len(self.__values)


def slow_fib(n: int) -> int:
    """Intentionally slow recursive Fibonacci."""
    if n < 2:
        return n
    return slow_fib(n - 1) + slow_fib(n - 2)

# Create LazyList of slow Fibonacci computations
lazy_fibs = LazyList([lambda n=n: slow_fib(n) for n in range(32, 37)])

print(lazy_fibs[0], lazy_fibs[1], lazy_fibs[2])

for i in lazy_fibs:
    print(i)

