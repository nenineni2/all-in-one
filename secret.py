from base64 import b85encode, b85decode
import codecs


message = input("Message > ")

method = input("Encode/decode > ").lower()

if method == "e":
    method = "encode"
elif method == "d":
    method = "decode"

assert method == "encode" or method == "decode"


match method:
    case "encode":
        print(
            b85encode(
                codecs.encode("".join(reversed(message)), "rot13").encode("utf-8")
            ).decode()
        )
    case "decode":
        print(
            "".join(
                reversed(
                    codecs.decode(
                        b85decode(
                            message.encode("utf-8"),
                        ).decode(),
                        "rot13",
                    )
                )
            )
        )
