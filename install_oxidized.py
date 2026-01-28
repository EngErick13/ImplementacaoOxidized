#!/usr/bin/env python3
import subprocess
import os
import sys

# Função para executar comandos no terminal e tratar erros
def executar_comando(comando, shell=False):
    print(f"Executando: {comando}")
    try:
        subprocess.run(comando, check=True, shell=shell)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar o comando: {e}")
        sys.exit(1)

def main():
    # Detecta o usuário que rodou o sudo para aplicar as permissões corretas
    candidato_usuario = os.getenv("SUDO_USER")
    if not candidato_usuario or candidato_usuario == "root":
        # Procura o primeiro usuário comum no diretório /home
        casas = [d for d in os.listdir('/home') if os.path.isdir(os.path.join('/home', d)) and d != 'lost+found']
        if casas:
            usuario = casas[0]
        else:
            usuario = "root"
    else:
        usuario = candidato_usuario

    # Define o novo caminho padrão em /opt/oxidized
    diretorio_home = os.path.expanduser(f"~{usuario}")
    caminho_config = "/opt/oxidized"
    
    print(f"--- Iniciando Instalação do Oxidized em {caminho_config} ---")

    # 1. Instalação de Dependências do Sistema
    print("Instalando dependências do sistema...")
    executar_comando(["apt-get", "update"])
    dependencias = [
        "ruby", "ruby-dev", "make", "gcc", "g++", "cmake", "libcurl4-openssl-dev", 
        "libssl-dev", "pkg-config", "libicu-dev", "libsqlite3-dev", "libyaml-dev", 
        "zlib1g-dev", "git", "rsync"
    ]
    executar_comando(["apt-get", "install", "-y"] + dependencias)

    # 2. Instalação das Gems do Ruby
    print("Instalando gems do Oxidized...")
    executar_comando(["gem", "install", "oxidized", "oxidized-web", "rugged"])

    # 3. Criação da Estrutura de Diretórios
    print(f"Criando diretórios em {caminho_config}...")
    os.makedirs(caminho_config, exist_ok=True)
    diretorio_backups = os.path.join(caminho_config, "configs")
    os.makedirs(diretorio_backups, exist_ok=True)
    os.makedirs(os.path.join(caminho_config, "model"), exist_ok=True)
    
    # 4. Configuração de Chaves SSH (Centralizado em /opt/oxidized/.ssh)
    diretorio_ssh = os.path.join(caminho_config, ".ssh")
    os.makedirs(diretorio_ssh, exist_ok=True)
    arquivo_chave = os.path.join(diretorio_ssh, "id_ed25519_github")

    # Ajusta permissões cedo para evitar erro de 'Permission Denied' no ssh-keygen
    executar_comando(f"chown -R {usuario}:{usuario} {caminho_config}", shell=True)

    # 5. Configuração do GitHub
    url_github = ""
    if len(sys.argv) > 1:
        url_github = sys.argv[1].strip()
    
    if not url_github:
        try:
            url_github = input("Digite a URL SSH do seu GitHub (ex: git@github.com:usuario/repo.git) ou deixe vazio: ").strip()
        except EOFError:
            url_github = ""
        
    if url_github and "github.com/" in url_github and "git@" not in url_github:
        # Formata URL HTTPS para SSH se necessário
        caminho_repo = url_github.split("github.com/")[-1].replace(".git", "")
        url_github = f"git@github.com:{caminho_repo}.git"
        print(f"URL formatada automaticamente para: {url_github}")

    # Gera chave SSH caso não exista
    if not os.path.exists(arquivo_chave):
        print("Gerando chave SSH para o GitHub...")
        executar_comando(f"sudo -u {usuario} ssh-keygen -t ed25519 -f {arquivo_chave} -N '' -C 'oxidized@backup'", shell=True)
        print("\nIMPORTANTE: Adicione esta chave pública ao seu GitHub:")
        with open(arquivo_chave + ".pub", "r") as f:
            print(f.read())
        try:
            input("Pressione Enter DEPOIS de adicionar a chave ao GitHub...")
        except EOFError:
            pass

    # Configura o arquivo SSH config no perfil do usuário para usar a chave em /opt
    diretorio_ssh_usuario = os.path.join(diretorio_home, ".ssh")
    os.makedirs(diretorio_ssh_usuario, exist_ok=True)
    executar_comando(f"chown {usuario}:{usuario} {diretorio_ssh_usuario}", shell=True)
    
    config_ssh = os.path.join(diretorio_ssh_usuario, "config")
    entrada_ssh = f"\nHost github.com\n  HostName github.com\n  User git\n  IdentityFile {arquivo_chave}\n  StrictHostKeyChecking no\n"
    
    if not os.path.exists(config_ssh) or arquivo_chave not in open(config_ssh).read():
        with open(config_ssh, "a") as f:
            f.write(entrada_ssh)
        executar_comando(f"chmod 600 {config_ssh}", shell=True)
        executar_comando(f"chown {usuario}:{usuario} {config_ssh}", shell=True)

    # 6. Inicialização dos Repositórios Git Locais
    if not os.path.exists(os.path.join(diretorio_backups, ".git")):
        executar_comando(f"sudo -u {usuario} git init {diretorio_backups}", shell=True)
        executar_comando(f"sudo -u {usuario} git -C {diretorio_backups} config user.name 'Oxidized'", shell=True)
        executar_comando(f"sudo -u {usuario} git -C {diretorio_backups} config user.email 'oxidized@backup.local'", shell=True)

    repositorio_sincronizacao = os.path.join(caminho_config, "repo_sync")
    if not os.path.exists(os.path.join(repositorio_sincronizacao, ".git")):
        os.makedirs(repositorio_sincronizacao, exist_ok=True)
        executar_comando(f"chown -R {usuario}:{usuario} {repositorio_sincronizacao}", shell=True)
        executar_comando(f"sudo -u {usuario} git -C {repositorio_sincronizacao} init", shell=True)
        
    if url_github:
        executar_comando(f"sudo -u {usuario} git -C {repositorio_sincronizacao} remote add origin {url_github} || sudo -u {usuario} git -C {repositorio_sincronizacao} remote set-url origin {url_github}", shell=True)

    # 7. Criação do arquivo de configuração do Oxidized (config)
    comando_hook = (
        f'git -C {caminho_config}/configs/ checkout master . 2>/dev/null; '
        f'REPO_DIR="{caminho_config}/repo_sync"; '
        'mkdir -p $REPO_DIR/equipamentos_configuracao $REPO_DIR/setup/model; '
        f'rsync -av --exclude ".git" {caminho_config}/configs/ $REPO_DIR/equipamentos_configuracao/; '
        'find $REPO_DIR/equipamentos_configuracao/ -maxdepth 1 -type f -exec mkdir -p $REPO_DIR/equipamentos_configuracao/default/ \\; -exec mv {} $REPO_DIR/equipamentos_configuracao/default/ \\;; '
        f'cp {caminho_config}/config $REPO_DIR/setup/config; '
        f'cp {caminho_config}/router.db $REPO_DIR/setup/router.db; '
        f'cp {caminho_config}/model/vrp.rb $REPO_DIR/setup/model/vrp.rb; '
        f'cp {caminho_config}/install_oxidized.py $REPO_DIR/setup/install_oxidized.py; '
        f'cp {caminho_config}/restore_oxidized.py $REPO_DIR/setup/restore_oxidized.py; '
        f'[ -f {caminho_config}/last_failures.log ] && cp {caminho_config}/last_failures.log $REPO_DIR/setup/last_failures.log; '
        'git -C $REPO_DIR config user.name "Oxidized"; '
        'git -C $REPO_DIR config user.email "oxidized@backup.local"; '
        'git -C $REPO_DIR add .; '
        'git -C $REPO_DIR commit -m "Sincronismo Automático: Estado do Projeto e Configurações" --allow-empty; '
        'git -C $REPO_DIR push origin master --force'
    )
    
    config_oxidized = f"""---
resolve_dns: true
interval: 3600
use_max_threads: false
threads: 30
timeout: 20
retries: 3
prompt: !ruby/regexp /^([\\w.@-]+[#>][\\s]?)$/
pid: "{caminho_config}/pid"
rest: 0.0.0.0:8888
extensions:
  oxidized-web:
    load: true
hooks:
  error_report:
    type: exec
    events: [node_fail]
    cmd: 'echo "$(date "+%Y-%m-%d %H:%M:%S") | Nodo: ${{OX_NODE_NAME}} | Status: ${{OX_JOB_STATUS}} | Erro: ${{OX_ERR_TYPE}} | Motivo: ${{OX_ERR_REASON}}" >> {caminho_config}/last_failures.log'
    async: true
  full_project_sync:
    type: exec
    events: [post_store]
    cmd: '{comando_hook}'
    async: true
input:
  default: ssh, telnet
  debug: false
  ssh:
    secure: false
output:
  default: git
  git:
    user: Oxidized
    email: oxidized@backup.local
    repo: "{caminho_config}/configs"
source:
  default: csv
  csv:
    file: "{caminho_config}/router.db"
    delimiter: !ruby/regexp /:/
    map:
      name: 0
      ip: 1
      model: 2
      username: 3
      password: 4
      group: 6
    vars_map:
      ssh_port: 5
"""
    with open(os.path.join(caminho_config, "config"), "w") as f:
        f.write(config_oxidized)
    
    # 8. Criação do arquivo router.db (Exemplo)
    arquivo_router_db = os.path.join(caminho_config, "router.db")
    if not os.path.exists(arquivo_router_db):
        with open(arquivo_router_db, "w") as f:
            f.write("# nome:ip:modelo:usuario:senha:porta_ssh:grupo\n")
            f.write("DUMMY_NODE:127.0.0.1:routeros:admin:admin:22:default\n")

    # 9. Configuração do Serviço no Systemd
    conteudo_servico = f"""[Unit]
Description=Oxidized - Backup de Configurações de Rede
After=network.target

[Service]
User={usuario}
Environment="OXIDIZED_HOME={caminho_config}"
ExecStart=/usr/local/bin/oxidized
Restart=on-failure
RestartSec=30s

[Install]
WantedBy=multi-user.target
"""
    print(f"Configurando serviço systemd para o usuário {usuario}...")
    with open("/etc/systemd/system/oxidized.service", "w") as f:
        f.write(conteudo_servico)
    
    os.chmod("/etc/systemd/system/oxidized.service", 0o644)
    executar_comando(["systemctl", "daemon-reload"])
    executar_comando(["systemctl", "enable", "oxidized"])
    
    # Limpa possíveis configurações antigas do root que podem causar erro
    if os.path.exists("/root/.config/oxidized"):
        executar_comando(["rm", "-rf", "/root/.config/oxidized"])

    executar_comando(["systemctl", "restart", "oxidized"])

    print("\n--- Instalação e Sincronização Desacoplada Concluída ---")
    print(f"Interface Web: http://<ip-da-maquina>:8888")
    print(f"Diretório Base: {caminho_config}")

if __name__ == "__main__":
    main()
