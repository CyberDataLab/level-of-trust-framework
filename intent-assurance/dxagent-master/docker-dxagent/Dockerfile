FROM python:3.10.12

RUN apt-get update && apt-get install -y \
    python3-dev \
    libnl-3-dev \
    libnl-route-3-dev \
    net-tools \
    sudo \
    --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Crear el usuario y el grupo antes de usarlos
RUN groupadd -r docker_dxagent_user && useradd -r -g docker_dxagent_user -m docker_dxagent_user

# Dar permisos de sudo al usuario docker_dxagent_user (sin contraseña)
RUN echo 'docker_dxagent_user ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/docker_dxagent_user

# Establecer la variable de entorno USER
ENV USER=docker_dxagent_user

# Darle permisos al directorio de la aplicación para el usuario
WORKDIR /app
COPY . /app/
COPY docker-dxagent/entrypoint.sh entrypoint.sh

RUN chown -R docker_dxagent_user:docker_dxagent_user /app

# Instalar las dependencias de la aplicación
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN chmod +x entrypoint.sh

# Establecer el usuario por defecto para el contenedor
USER docker_dxagent_user

ENTRYPOINT ["/app/entrypoint.sh"]