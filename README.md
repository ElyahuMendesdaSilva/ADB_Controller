# 📱 Gerenciador ADB Avançado

Um aplicativo multiplataforma (Windows, Linux e macOS) com interface gráfica feita em **[Flet](https://flet.dev/)** para gerenciar dispositivos Android via **ADB** (Android Debug Bridge).  
O projeto automatiza tarefas comuns como instalação/desinstalação de apps, controle de tela, monitoramento de desempenho, configurações de display e conexão ADB via Wi-Fi.

---

## Principais Funcionalidades

- **Gerenciamento de Dispositivos**
  - Detecta e conecta dispositivos via USB ou Wi-Fi.
  - Exibe nome, modelo, versão do Android e fabricante.
  - Indica status de conexão em tempo real.

- **Gerenciamento de Aplicativos**
  - Lista todos os apps instalados (usuário e sistema).
  - Desinstala aplicativos com um clique.
  - Exibe o nome real e o ícone de cada app.
  - Copia o *package name* facilmente.

- **Instalação de APKs**
  - Suporte a *drag and drop* ou seleção de arquivo.
  - Instalação automática via ADB com feedback visual.

- **Controle de Energia**
  - Reiniciar, desligar ou entrar em *fastboot mode*.

- **Espelhamento de Tela**
  - Inicia o **scrcpy** diretamente, com opções otimizadas de resolução e taxa de bits.
  - Bloqueia a interface enquanto o espelhamento está ativo.

- **Configurações de Tela**
  - Ajusta resolução, DPI e taxa de atualização via ADB.
  - Restaura configurações originais com um clique.

- **Integrações Avançadas**
  - Instala e ativa automaticamente o **Shizuku**.
  - Suporte experimental para configurar **Termux SSH**.

---

## Estrutura do Projeto

```
src/
├── assets/                 # Recursos visuais (ícones, imagens, etc)
├── back/                   # Backend (operações com ADB e scrcpy)
│   ├── back.py             # Núcleo lógico do backend
├── main.py                 # Interface gráfica (frontend com Flet)
```

---

## Instalação

### 1. Clone o repositório
```bash
git clone https://github.com/ElyahuMendesdaSilva/ADB_Controller.git
cd gerenciador-adb-avancado/src
```

### 2. Instale as dependências
```bash
pip install flet pyperclip requests
```

### 3. Execute o aplicativo
```bash
python main.py
```

> O programa baixa automaticamente o **ADB** e o **scrcpy** da internet, conforme o sistema operacional detectado.

---

## Tecnologias Utilizadas

| Tecnologia | Função |
|-------------|--------|
| **Python 3.10+** | Linguagem principal |
| **Flet** | Framework de interface gráfica |
| **ADB / scrcpy** | Comunicação e espelhamento Android |
| **Requests** | Downloads e APIs (GitHub, releases etc.) |
| **Threading** | Execução paralela de tarefas (monitoramento, ADB, logs) |

---

## Arquitetura

O projeto segue uma divisão clara entre **frontend (UI)** e **backend (operações ADB)**:

- **`main.py`**:  
  Gerencia toda a interface com Flet, incluindo abas, botões e lógica de interação.  
  Comunicação com `back.py` é feita via instâncias das classes `AppManager`, `ConfigManager` e `DeviceMonitor`.

- **`back/back.py`**:  
  Contém as classes de lógica de negócios:
  - `ADBManager`: baixa, valida e fornece caminhos para o ADB e scrcpy.
  - `AppManager`: gerencia pacotes, ícones e informações de apps.
  - `ConfigManager`: aplica configurações de display e obtém informações do sistema.
  - `DeviceMonitor`: monitora CPU, RAM, bateria e armazenamento em tempo real.

---

## Interface

A interface segue um tema escuro moderno e responsivo, inspirado em ferramentas profissionais de desenvolvimento Android.  
Os elementos visuais usam o sistema de cores centralizado em `theme_colors`.

---

## Recursos Planejados

- Logs avançados com filtros.
- Suporte completo ao `fastboot`.
- Backup e restauração de apps.
- Exportação de informações do dispositivo em JSON.

---

## Autor

**Elyahu Mendes**  

