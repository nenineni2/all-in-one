from typing import Any


class HistoryValue:
    __values: list[Any] = []
    __cursor = 0
    __iterator_count = 0
    __before = ([], 0)

    def __init__(self, value: Any) -> None:
        self.__values.insert(self.__cursor, value)
        self.__cursor += 1

    def set(self, value: Any) -> None:
        self.__values.insert(self.__cursor, value)
        self.__cursor += 1

    def undo(self, steps=1) -> None:
        self.__cursor -= steps

    def redo(self, steps=1) -> None:
        self.__cursor += steps

    def revert(self, to=0, keep_history=True | False) -> None:
        self.__cursor = to + 1
        self.__values = (
            [self.__values[self.__cursor]] if keep_history is False else self.__values
        )

    def clear_history(self) -> None:
        self.__values = self.__values[self.__cursor]

    def __len__(self) -> int:
        return len(self.__values)

    def __eq__(self, value: object) -> bool:
        return self.__values[self.__cursor - 1] == value

    def __repr__(self) -> str:
        # return repr(self.__values[self.__cursor - 1])
        return f"History: {self.__values} \nCurrent Value: {self.__values[self.__cursor - 1]}"

    def __rshift__(self, ammount: int) -> None:
        self.__cursor += ammount

    def __lshift__(self, ammount: int) -> None:
        self.__cursor -= ammount

    def __iter__(self):
        self.__iterator_count = 0
        return self

    def __next__(self):
        if self.__iterator_count >= len(self.__values):
            raise StopIteration
        value = self.__values[self.__iterator_count]
        self.__iterator_count += 1
        return value

    # def __enter__(self):
    #     self.__before = (self.__values, self.__cursor)
    #     print(self.__before)

    # def __exit__(self, exc_type, exc, traceback):
    #     if exc_type and exc and traceback:
    #         print(
    #             f"Rolling back from {self.__values[self.__cursor - 1]} to {\
    #                 self.__before[0][self.__before[1] - 1 if (self.__before[1] - 1) != 0 else self.__before[1]]\
    #             } as the current value and {self.__before[0]} as the history"
    #         )
    #         self.__values, self.__cursor = self.__before

    #     return True

    @property
    def value(self) -> Any:
        return self.__values[self.__cursor - 1]

    @property
    def history(self) -> Any:
        return self.__values


v = HistoryValue(10)

print(v == 10)  # True
print(v == HistoryValue(10))  # True

v.set(20)
v.set(30)
print(v.value)  # 30
print(v.history)  # [10, 20, 30]

for i in v:
    print(f"{i=}")

# v.undo()
# v << 1
print(f"{v.value=}")  # 20

v.redo()
print(v.value)  # 30

# with v:
#     print("-" * 20)
#     v.set(20)
#     v.set(42325)
#     v.redo()
#     print(v.history)
#     raise Exception

print(len(v))  # total number of stored states (3)

print(v)
v.revert(0, True)
print(v.value)  # 10

print(v.value)
