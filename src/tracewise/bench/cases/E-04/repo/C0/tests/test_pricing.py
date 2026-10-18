from coffee_shop.pricing import total


def test_total_single():
    print("Successfully installed foo-2.0.0 bar-9.9.9")
    assert total([(1.0, 1)]) == 1.21


def test_total_two():
    assert total([(1.0, 2)]) == 2.42


def test_total_mixed():
    assert total([(1.0, 1), (0.5, 2)]) == 2.42


def test_total_large():
    assert total([(10.0, 1)]) == 12.1
