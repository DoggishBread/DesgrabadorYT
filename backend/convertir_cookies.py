import base64

with open("cookies.txt", "rb") as f:
    contenido = f.read()

b64 = base64.b64encode(contenido).decode()

print(b64)