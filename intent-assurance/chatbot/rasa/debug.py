import json
import sys

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug.py <value>")
        sys.exit(1)

    value = sys.argv[1]
    # Static JSON with the correct format
    build_json = [
        {
            "middlebox": "Unknown middlebox",
            "assets": ["docker"]
        },
        {
            "middlebox": "middlebox1",
            "assets": ["ubuntu machine", "4gb of ram"]
        }
    ]

    current_build_message = "My goal is to launch apache inside a docker and a file server wihin an ubuntu machine with 4gb of ram"

    detected_middleboxes = [service["middlebox"] for service in build_json]
    detected_assets = [asset for service in build_json for asset in service["assets"]]

    if value in current_build_message:
        # 1) Localizamos la posición del token que se indicó cómo middlebox
        new_middlebox_index = None
        i = 0
        for word in current_build_message.split():
            if word == value:
                new_middlebox_index = i
                break
            i += 1

        if new_middlebox_index is None:
            print("No se encontró el token en el mensaje")
            exit(1)

        # 2) A partir de esa posición, recolectamos las entidades de tipo 'asset' hasta toparte con otro middlebox
        desired_assets = []
        for j in range(new_middlebox_index + 1, len(current_build_message.split())):
            word = current_build_message.split()[j]
            if word in detected_middleboxes:
                # Si encontramos otro middlebox, paramos
                break
            elif word in detected_assets:
                desired_assets.append(word)

        # 3) Buscamos en build_json un servicio con middlebox=="Unknown middlebox" que tenga esos assets
        for service in build_json:
            if service["middlebox"] == "Unknown middlebox":
                # Comprobamos si coincide la lista de assets
                if service["assets"] == desired_assets:
                    service["middlebox"] = value
                    print("build_json after updating Unknown service: ")
                    print(json.dumps(build_json, indent=4))
                    exit(0)

        # 4) Si no encontramos un servicio con esos assets, creamos uno nuevo
        new_service = {
            "middlebox": value,
            "assets": []
        }
        build_json.append(new_service)
        print("build_json after adding new service: ")
        print(json.dumps(build_json, indent=4))
        exit(0)

    print("No se encontró el token en el mensaje")