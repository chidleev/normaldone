from utils.standardizer import DataStandardizer


def test_replaces_latin_unit_in_number_pair() -> None:
    standardizer = DataStandardizer()
    result = standardizer.process_item({"length": "100 mm"})
    assert result["length"] == "100 мм"


def test_replaces_case_insensitive_russian_synonym() -> None:
    standardizer = DataStandardizer()
    result = standardizer.process_item({"weight": "5 Килограмм"})
    assert result["weight"] == "5 кг"


def test_replaces_multiple_units_in_one_string() -> None:
    standardizer = DataStandardizer()
    result = standardizer.process_item({"spec": "объем 2 Liter и длина 30 CM"})
    assert result["spec"] == "объем 2 л и длина 30 см"


def test_does_not_replace_inside_other_words() -> None:
    standardizer = DataStandardizer()
    result = standardizer.process_item({"text": "program should stay program"})
    assert result["text"] == "program should stay program"
