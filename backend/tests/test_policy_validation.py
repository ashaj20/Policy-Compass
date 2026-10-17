from app.policies.validation import display_filename


def test_display_filename_strips_paths_and_control_characters():
    assert display_filename("../../etc/evil\x00name.pdf") == "evilname.pdf"
    assert display_filename("C:\\Users\\x\\Repairs Policy.docx") == "Repairs Policy.docx"
    assert display_filename("") == "document"
    assert len(display_filename("a" * 500 + ".pdf")) == 200
