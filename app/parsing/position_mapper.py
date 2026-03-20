from app.schemas.document import Position


def build_position(page: int | None = None, paragraph_index: int | None = None) -> Position:
    return Position(page=page, paragraph_index=paragraph_index)
