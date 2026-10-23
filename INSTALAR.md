# Como instalar e testar o TUC7FJ

O sistema roda em **um computador da casa**, que funciona como servidor. Os celulares e tablets
conectados ao **mesmo Wi-Fi** acessam pelo navegador. Não é preciso internet durante a gira, só
o Wi-Fi.

## 1. Preparar o computador (só na primeira vez)

1. **Instale o Python:**
   1. Acesse <https://www.python.org/downloads/> e clique em "Download Python".
   2. Na primeira tela do instalador, **marque "Add python.exe to PATH"**.
   3. Clique em "Install Now".
2. **Baixe o sistema:**
   1. Entre no GitHub com a sua conta e abra o repositório **kahdamaso/7Flechas**.
   2. Troque o branch para **claude/confident-sagan-zykmvc**.
   3. Clique em **Code → Download ZIP**.
   4. Extraia o ZIP numa pasta fácil de achar, por exemplo `Documentos\TUC7FJ`.
3. **Baixe a planilha:**
   1. No Google Drive, abra a planilha **TUC7FJ**.
   2. Vá em **Arquivo → Fazer download → Microsoft Excel (.xlsx)**.

## 2. Ligar o sistema

**Windows:** dê dois cliques em **`iniciar.bat`**.

- Na primeira vez, ele leva alguns minutos instalando, e para isso precisa de internet.
- Se o Windows perguntar sobre o firewall, clique em **Permitir** (rede privada).

Quando estiver pronto, a janela mostra um endereço como este:

```
TUC7FJ no ar. Nos aparelhos da mesma rede, abra: http://192.168.0.10:8000
```

**Não feche essa janela durante a gira**: fechar a janela desliga o sistema.

> Mac/Linux: abra o Terminal na pasta e rode `./iniciar.sh`.

## 3. Importar os cadastros da planilha (só uma vez)

**Arraste o arquivo `.xlsx` baixado do Drive para cima do `importar.bat`.**

- Uma janela mostra o resumo da importação e o que precisa ser conferido à mão.
- O mesmo relatório fica salvo em `importacao-relatorio.txt`.
- A importação pode ser repetida sem duplicar nada.

> Mac/Linux: `./importar.sh caminho/da/planilha.xlsx`

## 4. Primeiro acesso

1. **No computador:** abra o navegador em `http://localhost:8000`.
   1. Crie a **senha da casa**. Ela vale para todos os aparelhos.
   2. Informe o seu nome como **responsável do dia**.
2. **No celular ou tablet:**
   1. Conecte ao mesmo Wi-Fi e abra o endereço mostrado na janela (`http://192.168...:8000`).
   2. Digite a senha da casa. O aparelho fica conectado por 30 dias.
   3. **Dica:** no menu do navegador, use **"Adicionar à tela inicial"**. O sistema passa a abrir como um aplicativo.

## 5. Roteiro para a gira de teste

Sugestão: na primeira gira, **mantenha a planilha em paralelo** e use o sistema ao mesmo tempo, para comparar.

1. **Antes da gira:** em **Giras → Nova gira**, escolha a data. O tipo é sugerido pelo dia da semana.
2. **Chamada:** marque SIM/NÃO para cada médium. Teste em dois aparelhos ao mesmo tempo.
3. **Inscrição (recepção):** digite o nome de quem chegou.
   - Confira se aparecem os alertas de retorno e de parentes.
   - Para quem não tem cadastro, use **Cadastro rápido**.
4. **Atendimento:** a pessoa do sistema fica com o celular ou tablet.
   1. Quando o cambone disser a entidade, toque nela e chame a pessoa sugerida.
   2. Na volta, marque **Atendido** e informe se houve retorno.
5. **Mapa:** no fim, compare a grade com a planilha.
6. **Depois da gira:** confira os **Retornos** e os **Relatórios**.

Anote tudo o que for estranho, lento ou confuso: o que esperava e o que aconteceu. Com essas
anotações, os ajustes ficam rápidos.

## Problemas comuns

| Problema | O que fazer |
|---|---|
| O celular não abre o endereço | Confira se está no **mesmo Wi-Fi** do computador. Libere o Python no firewall do Windows. |
| O endereço mudou | O roteador pode trocar o IP do computador. Use o endereço novo que aparece na janela. |
| O computador dormiu e o sistema parou | Desative a suspensão do computador durante a gira (Configurações → Energia). |
| Esqueci a senha da casa | No computador, abra um terminal na pasta e rode `.venv\Scripts\python -m flask --app run definir-senha`. |
| Quero voltar a uma cópia anterior | Desligue o sistema e copie um arquivo de `instance\backups\` por cima de `instance\tuc7fj.db`. |

**Seus dados ficam na pasta `instance`.** Não apague essa pasta, e copie `instance\backups`
periodicamente para um pendrive ou para o Drive.
