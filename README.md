# Conecta .md Converter

Ferramenta para conversão de arquivos **PDF** para **Markdown (.md)**.

Disponível em [versão web](https://conecta-inc.github.io/pdf-to-md-converter/).

Disponível em [**executável para Windows**](https://github.com/conecta-inc/pdf-to-md-converter/tree/main/dist).

Basta abrir, selecionar os PDFs e converter. Sem instalação, sem terminal e sem complicações.


---

## Funcionalidade principal

- Conversão de um ou múltiplos arquivos PDF para Markdown de uma só vez


---

## Como usar

### Opção 1 — Pelo navegador (qualquer sistema)

1. Abra o [conversor online](https://conecta-inc.github.io/pdf-to-md-converter/)
2. Arraste seus PDFs para a área indicada ou clique em **"Selecionar PDFs"**
3. Clique em **"Converter"**
4. Ao concluir, clique em **"Baixar todos os arquivos"** para salvar os `.md`

> Funciona em Windows, Mac e Linux. Os arquivos são processados localmente no seu navegador — nada é enviado para nenhum servidor.

> **Observação:** No Windows, ao abrir um arquivo `.md` baixado, o sistema pode exibir um aviso de segurança. Essa verificação é uma etapa necessária devido ao **Mark of the Web (MOTW)**, uma proteção do Windows que marca todo arquivo baixado da internet: é um comportamento normal e esperado. Basta selecionar **"Abrir no modo de exibição de Sintaxe"** para visualizar o conteúdo corretamente.

### Opção 2 — Executável Windows

1. Baixe o arquivo [`Conecta MD Converter.exe`](https://github.com/conecta-inc/pdf-to-md-converter/tree/main/dist)
2. Clique duas vezes para abrir
3. Clique em **"Selecionar PDFs"** e escolha os arquivos que deseja converter
4. (Opcional) Clique em **"Alterar"** para mudar a pasta de destino
5. Clique em **"Converter"**
6. Ao concluir, escolha entre **"Voltar para o conversor"** ou **"Encerrar programa e abrir diretório"**

> O executável é auto-contido. Não precisa instalar nada para usá-lo.


---

## Objetivos secundários do aplicativo

- Detecção automática de **headings** com base no tamanho da fonte
- Preservação de **negrito** e *itálico*
- Conversão de **listas** (com marcadores e numeradas)
- Extração de **tabelas** para formato Markdown
- Extração de **imagens** embutidas no PDF (salvas em pasta separada e referenciadas no .md)
- Preservação de **links/URLs**
- Escolha da pasta de destino (padrão: mesma pasta dos PDFs originais)
- Nomes de arquivo preservados: `relatorio.pdf` → `relatorio.md`

---

## Limitações conhecidas

- PDFs escaneados (imagens de texto sem OCR) não terão o texto extraído — apenas as imagens serão salvas
- A detecção de headings é baseada no tamanho relativo da fonte; PDFs com formatação incomum podem gerar headings imprecisos
- Tabelas muito complexas (com células mescladas) podem perder parte da estrutura na conversão

---


## Tecnologias utilizadas

| Tecnologia | Função |
|---|---|
| Python | Linguagem base (versão desktop) |
| PyMuPDF (fitz) | Extração de texto, tabelas e imagens dos PDFs (versão desktop) |
| tkinter | Interface gráfica nativa (versão desktop) |
| PyInstaller | Empacotamento em executável auto-contido (versão desktop) |
| JavaScript | Linguagem base (versão web) |
| pdf.js (Mozilla) | Leitura e parsing de PDFs no navegador (versão web) |