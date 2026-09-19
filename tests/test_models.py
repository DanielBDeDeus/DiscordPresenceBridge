from presence_bridge.models import AppConfig, CropRect, Rule


def test_config_round_trip():
    original = AppConfig(
        discord_application_id="123",
        allow_public_crop_relay=True,
        rules=[
            Rule(
                label="Firefox",
                process_match="firefox",
                crop=CropRect(10, 20, 300, 200),
            )
        ],
    )
    restored = AppConfig.from_dict(original.to_dict())
    assert restored.discord_application_id == "123"
    assert restored.rules[0].crop.width == 300
    assert restored.rules[0].process_match == "firefox"
