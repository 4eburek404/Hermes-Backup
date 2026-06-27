from flights_cli.pipeline._shared import (
    as_tuple,
    classify_market,
    is_direct_only,
    resolve_country_code,
)


class TestAsTuple:
    def test_none(self):
        assert as_tuple(None) == ()

    def test_list(self):
        assert as_tuple([1, 2]) == (1, 2)

    def test_tuple(self):
        assert as_tuple((3,)) == (3,)

    def test_scalar(self):
        assert as_tuple("SVO") == ("SVO",)


class TestClassifyMarket:
    def test_ru_domestic(self):
        assert classify_market("RU", "RU") == "ru_domestic"

    def test_ru_touching(self):
        assert classify_market("RU", "TR") == "ru_touching_international"
        assert classify_market("TR", "RU") == "ru_touching_international"

    def test_global_non_ru(self):
        assert classify_market("TR", "DE") == "global_non_ru"

    def test_structurally_constrained(self):
        assert classify_market(None, "RU") == "ru_touching_international"
        assert classify_market("RU", None) == "ru_touching_international"
        assert classify_market(None, None) == "structurally_constrained"
        assert classify_market(None, "TR") == "structurally_constrained"
        assert classify_market("TR", None) == "structurally_constrained"


class TestIsDirectOnly:
    def test_direct(self):
        assert (
            is_direct_only({"max_connections": 0, "tier2_max_connections": 0}) is True
        )

    def test_not_direct(self):
        assert (
            is_direct_only({"max_connections": 1, "tier2_max_connections": 0}) is False
        )

    def test_missing_keys(self):
        assert is_direct_only({}) is False


class TestResolveCountryCode:
    def test_unknown_code(self):
        class FakeStore:
            airport_by_code = {}
            city_by_code = {}

            def resolve_location(self, code):
                raise ValueError("not found")

        assert resolve_country_code(FakeStore(), "XXX") is None

    def test_airport_lookup(self):
        class FakeStore:
            airport_by_code = {"SVO": {"country_code": "RU"}}
            city_by_code = {}

            def resolve_location(self, code):
                raise ValueError("not found")

        assert resolve_country_code(FakeStore(), "svo") == "RU"

    def test_city_lookup(self):
        class FakeStore:
            airport_by_code = {}
            city_by_code = {"MOW": {"country_code": "RU"}}

            def resolve_location(self, code):
                raise ValueError("not found")

        assert resolve_country_code(FakeStore(), "MOW") == "RU"

    def test_resolve_location_fallback(self):
        """When airport/city dicts don't contain the code but resolve_location does."""

        class Location:
            country_code = "RU"

        class FakeStore:
            airport_by_code = {}
            city_by_code = {}

            def resolve_location(self, code):
                return Location()

        assert resolve_country_code(FakeStore(), "LED") == "RU"
