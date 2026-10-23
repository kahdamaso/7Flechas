import click

from .extensions import db
from .importacao import importar
from .models import definir_senha_casa, garantir_linhas_padrao


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

    @app.cli.command("definir-senha")
    @click.password_option("--senha", prompt="Nova senha da casa")
    def definir_senha(senha):
        """Define (ou redefine, se esquecida) a senha de acesso da casa."""
        if len(senha) < 6:
            raise click.BadParameter("use pelo menos 6 caracteres")
        definir_senha_casa(senha)
        db.session.commit()
        click.echo("Senha da casa definida.")

    @app.cli.command("importar")
    @click.argument("caminho", type=click.Path(exists=True))
    def importar_cmd(caminho):
        """Importa os cadastros da planilha (.xlsx baixado do Drive ou pasta com CSVs)."""
        relatorio = importar(caminho)
        click.echo(relatorio.texto())
