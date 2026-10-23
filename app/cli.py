import click

from .extensions import db
from .importacao import importar
from .models import garantir_linhas_padrao


def registrar_comandos(app):
    @app.cli.command("init-db")
    @click.option("--apagar", is_flag=True, help="Apaga todas as tabelas antes de recriar.")
    def init_db(apagar):
        """Cria as tabelas do banco (e as linhas de trabalho padrão)."""
        if apagar:
            click.confirm("Isto apaga TODOS os dados. Continuar?", abort=True)
            db.drop_all()
        db.create_all()
        garantir_linhas_padrao()
        click.echo("Banco pronto.")

    @app.cli.command("importar")
    @click.argument("caminhos", nargs=-1, required=True, type=click.Path(exists=True))
    @click.option("--substituir", is_flag=True, help="Reimporta sessões que já têm atendimentos.")
    @click.option("--ano", type=int, help="Ano para datas sem ano na planilha de presença.")
    def importar_cmd(caminhos, substituir, ano):
        """Importa os CSVs (arquivos ou pastas) para o banco."""
        relatorio = importar(caminhos, substituir=substituir, ano=ano)
        click.echo(relatorio.texto())
