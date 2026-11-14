"""Starter data for new accounts, committed together with their owner."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import Tag, TagRelationship, Task, TaskBlock, User
from app.services.scoring import DEFAULT_SCORING_FORMULA


def add_onboarding_data(db: Session, user: User) -> None:
    """Call only during account creation; the caller owns commit and rollback."""
    db.flush()
    created_at = user.created_at
    creation_date = created_at.astimezone().date()
    tags: dict[str, Tag] = {}
    for name, parent, value, color, description in (
        (
            "Pessoal",
            None,
            0,
            "#3F7D63",
            "Organização da vida pessoal. Valor 0: apenas organização.",
        ),
        ("Rotina", "Pessoal", 0, None, "Atividades do dia a dia. Valor 0: apenas organização."),
        ("Aprendizado", "Pessoal", 1, None, "Estudos, experiências e desenvolvimento pessoal."),
        (
            "Trabalho",
            None,
            0,
            "#4C79A8",
            "Organização das atividades profissionais. Valor 0: apenas organização.",
        ),
        ("Projetos", "Trabalho", 1, None, "Entregas e iniciativas em andamento."),
        ("Administrativo", "Trabalho", 0, None, "Atividades administrativas e manutenção."),
        (
            "Urgente",
            None,
            5,
            "#D64545",
            "Compromissos que precisam de atenção especial. "
            "Valor 5: +100 pontos na fórmula padrão.",
        ),
    ):
        tag = Tag(
            user_id=user.id,
            name=name,
            score_value=value,
            color=tags[parent].color if parent else color,
            description=description,
        )
        db.add(tag)
        tags[name] = tag
        if parent:
            db.add(TagRelationship(child=tag, parent=tags[parent]))

    previous: Task | None = None
    for title, priority, tag, due_days, description in (
        (
            "Conheça sua próxima tarefa",
            4,
            "Aprendizado",
            None,
            "O Next Task recomenda o que merece sua atenção. Registre o que precisa fazer "
            "e consulte **Next** quando quiser começar.\n\n"
            "### Como a pontuação funciona\n\n"
            "A fórmula padrão combina:\n\n"
            "- **Prioridade × 25:** cada ponto de prioridade adiciona 25 pontos.\n"
            "- **Idade em dias × 0,25:** tarefas antigas ganham atenção aos poucos.\n"
            "- **Dias sem trabalhar × 1:** o tempo desde Worked now aumenta a pontuação. "
            "Antes do primeiro registro de trabalho, conta desde a criação da tarefa.\n"
            "- **Valor das tags × 20:** soma as tags diretas e suas ancestrais, "
            "contando cada tag uma vez. **Urgente**, com valor 5, adiciona 100 pontos. "
            "Uma tag com valor 0 serve apenas para organização.\n"
            "- **Prazo:** um prazo futuro ganha influência conforme se aproxima. "
            "No dia do vencimento, adiciona 50 pontos; depois, mais 20 por dia de atraso. "
            "Sem prazo, essa parcela é zero.\n\n"
            "A expressão completa é:\n\n"
            f"```text\n{DEFAULT_SCORING_FORMULA}\n```\n\n"
            "Na expressão, priority é a prioridade; ageDays, a idade; idleDays, os dias "
            "sem trabalhar; tagValue, a soma dos valores das tags; hasDueDate indica "
            "se há prazo; dueOffsetDays é a diferença em dias entre hoje e o prazo "
            "(negativa antes do vencimento). exp é a função exponencial.\n\n"
            "### Quando uma tarefa é marcada como trabalhada\n\n"
            "Clique em **Worked now** quando tiver dedicado atenção à tarefa, mesmo "
            "sem concluí-la. O app registra a data e a hora atuais em **Last worked**. "
            "Esse registro também é atualizado ao iniciar um período de foco com a "
            "tarefa e ao bloquear ou reativar um bloqueio dela. Você pode corrigir "
            "a data manualmente no campo Last worked.\n\n"
            "A contagem de **idleDays** recomeça do zero, reduzindo a parcela da "
            "pontuação ligada ao tempo sem trabalhar. A idade e o prazo continuam "
            "contando normalmente. A tarefa continua pendente até você concluí-la "
            "ou abandoná-la.\n\n"
            "### Como a próxima tarefa é escolhida\n\n"
            "Entre as tarefas elegíveis, a maior pontuação é recomendada primeiro. "
            "Tarefas bloqueadas, concluídas ou abandonadas ficam fora dessa seleção. "
            "Quando há subtarefas pendentes, o app recomenda uma ação filha antes do pai "
            "e pode usar a pontuação do pai para dar prioridade a ela. "
            "Você pode personalizar a fórmula em **Settings**.\n\n"
            "Estes quatro exemplos usam dependências normais para apresentar uma etapa "
            "de cada vez. Conclua este exemplo com **Finish** para liberar o próximo. "
            "Abandon task também libera dependências, sem registrar conclusão.",
        ),
        (
            "Experimente as tags e seus valores",
            3,
            "Projetos",
            None,
            "Esta tarefa usa **Projetos**, uma subtag de **Trabalho**. Ao aplicar uma "
            "subtag, suas tags ancestrais também são consideradas.\n\n"
            "Abra **Tags** e experimente alterar o valor de Projetos. Volte para "
            "conferir a pontuação desta tarefa. Use valor 0 nas tags que deseja manter "
            "apenas para organização. **Urgente** é uma tag de alto nível, vermelha, "
            "com valor 5; você pode combinar tags de assuntos diferentes.\n\n"
            "Conclua este exemplo com **Finish** para liberar o exemplo de prazo.",
        ),
        (
            "Experimente uma tarefa com prazo",
            2,
            "Rotina",
            7,
            "Este exemplo recebeu um prazo de **7 dias após a criação da sua conta**. "
            "Conforme o prazo se aproxima, sua influência na pontuação aumenta.\n\n"
            "Abra os detalhes e experimente mudar ou remover a data. Nas suas tarefas "
            "reais, use prazo quando existir um compromisso de data.\n\n"
            "Esta tarefa estava bloqueada pela anterior: as dependências impedem que "
            "um prazo faça uma etapa aparecer antes do seu pré-requisito. Conclua com "
            "**Finish** para liberar o último exemplo.",
        ),
        (
            "Adicione algo que você não quer esquecer",
            1,
            "Aprendizado",
            None,
            "Crie sua primeira tarefa real: algo pequeno que você precisa fazer. "
            "Escolha uma tag e ajuste a prioridade conforme sua necessidade.\n\n"
            "Conclua este exemplo e consulte a próxima recomendação. Use **Start focus** "
            "quando quiser trabalhar com o temporizador. Todos estes exemplos são "
            "tarefas normais: você pode editar, concluir, abandonar ou excluir.",
        ),
    ):
        task = Task(
            user_id=user.id,
            title=title,
            description=description,
            priority=priority,
            tags=[tags[tag]],
            due_date=creation_date + timedelta(days=due_days) if due_days else None,
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(task)
        if previous is not None:
            db.add(TaskBlock(task=task, blocking_task=previous, blocked_at=created_at))
        previous = task
