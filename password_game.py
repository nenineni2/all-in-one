from prompt_toolkit import prompt
from random import choices
from string import ascii_letters

zeichenfolge: str = "".join(choices([*ascii_letters, *[str(i) for i in range(9)]], k=5))

regeln = [
    (lambda x: len(x) >= 5, "Dein Passwort muss länger als 5 Zeichen lang sein."),
    (
        lambda s: any(ch.isdigit() for ch in s),
        "Dein Passwort muss eine Zahl enthalten.",
    ),
    (
        lambda s: any(ch.isupper() for ch in s),
        "Dein Passwort muss ein Großbuchstaben enthalten.",
    ),
    (
        lambda s: any(not ch.isalnum() and not ch.isspace() for ch in s),
        "Dein Passwort muss ein Sonderzeichen enthalten.",
    ),
    (
        lambda s: sum(int(i) if i.isnumeric() else 0 for i in s) == 25,
        "Die Summe aller Zahlen in deinem Passwort muss 25 ergeben.",
    ),
    (
        lambda s: any(
            value in s
            for value in [
                "Januar",
                "Februar",
                "März",
                "April",
                "Mai",
                "Juni",
                "Juli",
                "August",
                "September",
                "Oktober",
                "November",
                "Dezember",
            ]
        ),
        "Dein Passwort muss einen Monat enthalten.",
    ),
    (
        lambda s: any(value in s for value in ["Pepse", "Stabux", "Schel"]),
        "Dein Passwort muss einen unserer Sponsoren enthalten (`Pepse`, `Stabux`, `Schel`)",
    ),
    (
        lambda s: zeichenfolge in s,
        f"Dein Passwort muss diese Kombi an Zeichen enthalten: `{zeichenfolge}`",
    ),
]
# lambda s: any(not ch.isalnum() and not ch.isspace() for ch in s)

i = 0
letzes_passwort: str = ""

while i < len(regeln):
    print("\033[H\033[2J", end="")

    for r in regeln[:i]:
        if not r[0](letzes_passwort):
            print("\033[H\033[2J", end="")
            print(f"{r[1]}")
            passwort = prompt("Passwort Eingeben: ", default=letzes_passwort)
            letzes_passwort = passwort
            break

    if regeln[i][0](letzes_passwort):
        i += 1
        continue

    regel: str = regeln[i][1]
    print(f"{regel}")

    passwort = prompt("Passwort Eingeben: ", default=letzes_passwort)
    letzes_passwort = passwort

    if passwort != "":
        if regeln[i][0](passwort):
            i += 1

print("ws in den chat")
