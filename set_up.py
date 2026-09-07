# Window: 800px board plus a right sidebar for turn / eval / material.
BOARD_SIZE = 800
SQUARE_SIZE = BOARD_SIZE // 8
SIDEBAR_WIDTH = 260
SCREEN_WIDTH = BOARD_SIZE + SIDEBAR_WIDTH
SCREEN_HEIGHT = 800

# Light/dark wood colors for the squares.
LIGHT_SQUARE = (240, 217, 181)
DARK_SQUARE = (181, 136, 99)

# Piece drawing colors (Unicode chess glyphs, not sprites).
WHITE_PIECE = (255, 255, 255)
BLACK_PIECE = (20, 20, 20)

# Sidebar
SIDEBAR_BG = (36, 36, 40)
SIDEBAR_PANEL = (48, 48, 54)
SIDEBAR_TEXT = (230, 230, 230)
SIDEBAR_MUTED = (160, 160, 170)
SIDEBAR_ACCENT = (210, 180, 120)

# Map engine letters to chess symbols. Uppercase = White, lowercase = Black.
piece_conversion = {
   "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
   "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
   ".": "",
}
