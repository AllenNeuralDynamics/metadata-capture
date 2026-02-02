"""Tests for schema validation logic."""

from agent.validation import validate_metadata, VALID_SEX


class TestRequiredFields:
    """Test required field detection."""

    def test_all_required_present(self):
        metadata = {
            "subject": {"subject_id": "553429"},
            "data_description": {
                "modality": [{"name": "Planar optical physiology", "abbreviation": "pophys"}],
                "project_name": "BrainMap",
            },
        }
        result = validate_metadata(metadata)
        assert len(result.missing_required) == 0

    def test_all_required_missing(self):
        result = validate_metadata({})
        assert set(result.missing_required) == {
            "subject.subject_id",
            "data_description.modality",
            "data_description.project_name",
        }

    def test_partial_required(self):
        metadata = {"subject": {"subject_id": "553429"}}
        result = validate_metadata(metadata)
        assert "subject.subject_id" not in result.missing_required
        assert "data_description.modality" in result.missing_required


class TestEnumValidation:
    """Test controlled vocabulary validation."""

    def test_valid_sex(self):
        for sex in VALID_SEX:
            metadata = {"subject": {"sex": sex}}
            result = validate_metadata(metadata)
            errors = [i for i in result.issues if i.field == "subject.sex" and i.severity == "error"]
            assert len(errors) == 0, f"'{sex}' should be valid"

    def test_invalid_sex(self):
        metadata = {"subject": {"sex": "unknown_value"}}
        result = validate_metadata(metadata)
        errors = [i for i in result.issues if i.field == "subject.sex" and i.severity == "error"]
        assert len(errors) == 1

    def test_valid_modality(self):
        for abbr in ["ecephys", "pophys", "SPIM", "behavior"]:
            metadata = {"data_description": {"modality": [{"abbreviation": abbr}]}}
            result = validate_metadata(metadata)
            errors = [i for i in result.issues if "modality" in i.field and i.severity == "error"]
            assert len(errors) == 0, f"'{abbr}' should be valid"

    def test_invalid_modality(self):
        metadata = {"data_description": {"modality": [{"abbreviation": "xray"}]}}
        result = validate_metadata(metadata)
        errors = [i for i in result.issues if "modality" in i.field and i.severity == "error"]
        assert len(errors) == 1

    def test_valid_species(self):
        metadata = {"subject": {"species": {"name": "Mus musculus"}}}
        result = validate_metadata(metadata)
        warnings = [i for i in result.issues if "species" in i.field]
        assert len(warnings) == 0

    def test_unknown_species(self):
        metadata = {"subject": {"species": {"name": "Canis lupus"}}}
        result = validate_metadata(metadata)
        warnings = [i for i in result.issues if "species" in i.field]
        assert len(warnings) == 1


class TestFormatValidation:
    """Test format checks."""

    def test_valid_subject_id(self):
        metadata = {"subject": {"subject_id": "553429"}}
        result = validate_metadata(metadata)
        warnings = [i for i in result.issues if i.field == "subject.subject_id"]
        assert len(warnings) == 0

    def test_short_subject_id(self):
        metadata = {"subject": {"subject_id": "12"}}
        result = validate_metadata(metadata)
        warnings = [i for i in result.issues if i.field == "subject.subject_id"]
        assert len(warnings) == 1

    def test_valid_coordinates(self):
        metadata = {"procedures": {"coordinates": {"x": 20.0, "y": 50.0}}}
        result = validate_metadata(metadata)
        assert "procedures.coordinates" in result.valid_fields

    def test_positive_thickness(self):
        metadata = {"procedures": {"section_thickness_um": 10.0}}
        result = validate_metadata(metadata)
        assert "procedures.section_thickness_um" in result.valid_fields

    def test_negative_thickness(self):
        metadata = {"procedures": {"section_thickness_um": -5.0}}
        result = validate_metadata(metadata)
        errors = [i for i in result.issues if i.field == "procedures.section_thickness_um"]
        assert len(errors) == 1


class TestCrossFieldConsistency:
    """Test cross-field validation rules."""

    def test_physiology_modality_warns_without_session(self):
        metadata = {
            "data_description": {"modality": [{"abbreviation": "ecephys"}]},
        }
        result = validate_metadata(metadata)
        warnings = [i for i in result.issues if i.field == "session"]
        assert len(warnings) == 1

    def test_non_physiology_no_session_warning(self):
        metadata = {
            "data_description": {"modality": [{"abbreviation": "SPIM"}]},
        }
        result = validate_metadata(metadata)
        warnings = [i for i in result.issues if i.field == "session"]
        assert len(warnings) == 0


class TestCompletenessScore:
    """Test completeness scoring."""

    def test_full_completeness(self):
        metadata = {
            "subject": {"subject_id": "553429"},
            "data_description": {
                "modality": [{"abbreviation": "pophys"}],
                "project_name": "BrainMap",
            },
        }
        result = validate_metadata(metadata)
        assert result.completeness_score == 1.0

    def test_zero_completeness(self):
        result = validate_metadata({})
        assert result.completeness_score == 0.0

    def test_partial_completeness(self):
        metadata = {"subject": {"subject_id": "553429"}}
        result = validate_metadata(metadata)
        assert 0.0 < result.completeness_score < 1.0


class TestValidationResult:
    """Test the ValidationResult output format."""

    def test_to_dict_structure(self):
        metadata = {
            "subject": {"subject_id": "553429", "sex": "invalid"},
            "data_description": {"modality": [{"abbreviation": "pophys"}]},
        }
        result = validate_metadata(metadata)
        d = result.to_dict()
        assert "status" in d
        assert "completeness_score" in d
        assert "errors" in d
        assert "warnings" in d
        assert "missing_required" in d
        assert "valid_fields" in d
        assert isinstance(d["errors"], list)
        assert isinstance(d["warnings"], list)

    def test_valid_status(self):
        metadata = {
            "subject": {"subject_id": "553429"},
            "data_description": {
                "modality": [{"abbreviation": "SPIM"}],
                "project_name": "BrainMap",
            },
        }
        result = validate_metadata(metadata)
        assert result.status == "valid"

    def test_error_status(self):
        metadata = {
            "subject": {"sex": "invalid"},
            "data_description": {"modality": [{"abbreviation": "xray"}]},
        }
        result = validate_metadata(metadata)
        assert result.status == "errors"
