from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_production_code_contains_no_demo_story_content() -> None:
    production_files = [
        *ROOT.glob("backend/src/scriptnow/**/*.py"),
        *ROOT.glob("frontend/apps/creator/src/**/*.ts"),
        *ROOT.glob("frontend/apps/creator/src/**/*.vue"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in production_files)

    forbidden_demo_content = (
        "真相追逐：越接近答案，越失去自我",
        "禁忌共生：爱意味着交出控制权",
        "倒计时审判：拯救多数还是承认少数",
        "一封盖着未来日期邮戳的旧信",
        "守灯人后代",
        "The Rejected Bond",
        "The Binding Throne",
    )
    for phrase in forbidden_demo_content:
        assert phrase not in combined


def test_creation_wizard_does_not_preselect_story_shape_or_size() -> None:
    wizard = (
        ROOT / "frontend/apps/creator/src/views/WizardPage.vue"
    ).read_text(encoding="utf-8")

    assert "const structure = ref('')" in wizard
    assert "const creativeLanguage = ref('')" in wizard
    assert "const volumeOne = ref<number | null>(null)" in wizard
    assert "const volumeTwo = ref<number | null>(null)" in wizard
    assert "const volumeThree = ref<number | null>(null)" in wizard
    assert "const novelChapterTargetWords = ref<number | null>(null)" in wizard
