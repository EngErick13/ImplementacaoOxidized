#!/usr/bin/env python3
import subprocess
import os
import sys
import shutil

# Função para executar comandos no terminal
def executar_comando(comando, shell=False):
    print(f"Executando: {comando}")
    try:
        subprocess.run(comando, check=True, shell=shell)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar comando: {e}")
        return False
    return True

def main():
    # Detecta o usuário comum para aplicar as permissões
    candidato_usuario = os.getenv("SUDO_USER")
    if not candidato_usuario or candidato_usuario == "root":
        casas = [d for d in os.listdir('/home') if os.path.isdir(os.path.join('/home', d)) and d != 'lost+found']
        if casas:
            usuario = casas[0]
        else:
            usuario = "root"
    else:
        usuario = candidato_usuario

    diretorio_home = os.path.expanduser(f"~{usuario}")
    caminho_config = "/opt/oxidized"
    clone_temporario = "/tmp/oxidized_recovery"
    
    print("--- Iniciando Recuperação de Desastres do Oxidized ---")

    # 1. Obtém a URL do GitHub
    url_github = ""
    if len(sys.argv) > 1:
        url_github = sys.argv[1].strip()
    
    if not url_github:
        try:
            url_github = input("Digite a URL SSH do seu repositório GitHub (ex: git@github.com:user/repo.git): ").strip()
        except EOFError:
            print("Erro: URL do GitHub é necessária para a recuperação.")
            sys.exit(1)

    if not url_github:
        print("URL do GitHub é necessária para a recuperação.")
        sys.exit(1)

    # Formatação automática de URL HTTPS para SSH
    if "github.com/" in url_github and "git@" not in url_github:
        caminho_repo = url_github.split("github.com/")[-1].replace(".git", "")
        url_github = f"git@github.com:{caminho_repo}.git"
        print(f"URL formatada automaticamente para: {url_github}")

    # 2. Instalação do Git se necessário
    print("Verificando dependências básicas (git)...")
    executar_comando(["apt-get", "update"])
    executar_comando(["apt-get", "install", "-y", "git"])

    # 3. Configuração da Chave SSH (Centralizado em /opt/oxidized/.ssh)
    diretorio_ssh = os.path.join(caminho_config, ".ssh")
    arquivo_chave = os.path.join(diretorio_ssh, "id_ed25519_github")
    
    if not os.path.exists(arquivo_chave):
        print("Chave SSH não encontrada. Gerando nova chave para acesso ao GitHub...")
        os.makedirs(diretorio_ssh, exist_ok=True)
        # Ajusta permissões antes para evitar erro de 'Permission Denied'
        executar_comando(f"chown -R {usuario}:{usuario} {caminho_config}", shell=True)
        executar_comando(f"sudo -u {usuario} ssh-keygen -t ed25519 -f {arquivo_chave} -N '' -C 'oxidized@recovery'", shell=True)
        print("\nIMPORTANTE: Adicione esta chave pública ao seu GitHub:")
        with open(arquivo_chave + ".pub", "r") as f:
            print(f.read())
        input("Pressione Enter DEPOIS de adicionar a chave ao GitHub para continuar...")

    # Garante que o SSH local do usuário aponte para a chave em /opt
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

    # 4. Clonagem do Repositório
    if os.path.exists(clone_temporario):
        shutil.rmtree(clone_temporario)
    
    print(f"Clonando repositório de backup: {url_github}")
    if not executar_comando(f"sudo -u {usuario} git clone {url_github} {clone_temporario}", shell=True):
        print("Falha ao clonar o repositório. Verifique suas permissões no GitHub.")
        sys.exit(1)

    # 5. Executa script de instalação para garantir dependências e serviço
    print("Finalizando ambiente (Executando instalador)...")
    instalador = os.path.join(caminho_config, "install_oxidized.py")
    if os.path.exists(instalador):
        executar_comando(f"sudo python3 {instalador} '{url_github}'", shell=True)

    # 6. RESTAURAÇÃO DOS DADOS DO GIT
    print("Aplicando dados restaurados do Git sobre as configurações...")
    pasta_setup = os.path.join(clone_temporario, "setup")
    if os.path.exists(pasta_setup):
        os.makedirs(caminho_config, exist_ok=True)
        shutil.copy2(os.path.join(pasta_setup, "config"), os.path.join(caminho_config, "config"))
        shutil.copy2(os.path.join(pasta_setup, "router.db"), os.path.join(caminho_config, "router.db"))
        
        origem_modelo = os.path.join(pasta_setup, "model")
        if os.path.exists(origem_modelo):
            os.makedirs(os.path.join(caminho_config, "model"), exist_ok=True)
            for arquivo in os.listdir(origem_modelo):
                shutil.copy2(os.path.join(origem_modelo, arquivo), os.path.join(caminho_config, "model", arquivo))
        
        # Protege os próprios scripts salvando-os em /opt/oxidized
        shutil.copy2(os.path.join(pasta_setup, "install_oxidized.py"), os.path.join(caminho_config, "install_oxidized.py"))
        shutil.copy2(os.path.join(pasta_setup, "restore_oxidized.py"), os.path.join(caminho_config, "restore_oxidized.py"))

        # NORMALIZAÇÃO DE CAMINHOS: Ajusta o config restaurado para o novo padrão /opt/oxidized
        print("Normalizando caminhos no arquivo config...")
        arquivo_config = os.path.join(caminho_config, "config")
        if os.path.exists(arquivo_config):
            with open(arquivo_config, "r") as f:
                conteudo = f.read()
            
            # Substitui o caminho antigo pelo novo
            novo_conteudo = conteudo.replace("/home/erick/.config/oxidized", "/opt/oxidized")
            # Garante que referências aos scripts também sejam corrigidas
            novo_conteudo = novo_conteudo.replace("/home/erick/install_oxidized.py", "/opt/oxidized/install_oxidized.py")
            novo_conteudo = novo_conteudo.replace("/home/erick/restore_oxidized.py", "/opt/oxidized/restore_oxidized.py")
            
            with open(arquivo_config, "w") as f:
                f.write(novo_conteudo)

    # Restaura o histórico de backup dos equipamentos
    print("Restaurando histórico de backups dos equipamentos...")
    origem_backup = os.path.join(clone_temporario, "equipamentos_configuracao")
    diretorio_backups = os.path.join(caminho_config, "configs")
    if os.path.exists(origem_backup):
        os.makedirs(diretorio_backups, exist_ok=True)
        if not os.path.exists(os.path.join(diretorio_backups, ".git")):
            executar_comando(f"sudo -u {usuario} git -C {diretorio_backups} init", shell=True)
            executar_comando(f"sudo -u {usuario} git -C {diretorio_backups} config user.name 'Oxidized'", shell=True)
            executar_comando(f"sudo -u {usuario} git -C {diretorio_backups} config user.email 'oxidized@backup.local'", shell=True)
        
        # Copia os backups restaurados para o pool local
        for item in os.listdir(origem_backup):
            o = os.path.join(origem_backup, item)
            d = os.path.join(diretorio_backups, item)
            if os.path.isdir(o):
                shutil.copytree(o, d, dirs_exist_ok=True)
            else:
                shutil.copy2(o, d)
        
        # Commita a restauração para garantir que o histórico apareça na aba 'Versions'
        executar_comando(f"sudo -u {usuario} git -C {diretorio_backups} add .", shell=True)
        try:
            executar_comando(f"sudo -u {usuario} git -C {diretorio_backups} commit -m 'Restaurado via Git Backup' --allow-empty", shell=True)
        except: pass

    # Corrige permissões finais e reinicia o serviço
    print("Finalizando permissões e reiniciando serviço...")
    executar_comando(f"chown -R {usuario}:{usuario} {caminho_config}", shell=True)
    executar_comando("systemctl restart oxidized", shell=True)

    print("\n--- RECUPERAÇÃO CONCLUÍDA ---")
    print(f"O sistema foi restaurado em {caminho_config}.")
    print("O serviço Oxidized deve estar rodando. Verifique com: sudo systemctl status oxidized")

if __name__ == "__main__":
    main()
