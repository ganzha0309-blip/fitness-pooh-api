def trainings_payload() -> list[dict]:
    return [
        {
            "id": "morning",
            "title": "Утренняя зарядка",
            "description": "Мягкий запуск дня: суставы, дыхание, легкий тонус.",
            "subscription": "free",
            "category": "Дом",
            "duration": "10 мин",
        },
        {
            "id": "back-warmup",
            "title": "Разминка для спины",
            "description": "Снимает зажимы после сидячего дня и готовит к тренировке.",
            "subscription": "free",
            "category": "Мобилити",
            "duration": "12 мин",
        },
        {
            "id": "press-base",
            "title": "Интенсив на пресс",
            "description": "Короткая тренировка корпуса для Base-подписки.",
            "subscription": "base",
            "category": "Кор",
            "duration": "18 мин",
        },
        {
            "id": "mass-a",
            "title": "Массонабор: тренировка A",
            "description": "Базовая силовая схема для прогресса в объеме.",
            "subscription": "pro",
            "category": "Зал",
            "duration": "55 мин",
        },
        {
            "id": "vip-plan",
            "title": "Личная схема от Пуха",
            "description": "VIP-программа под цель, график и восстановление.",
            "subscription": "vip",
            "category": "Персонально",
            "duration": "Индивидуально",
        },
    ]
