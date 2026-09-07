from engine import *
import engine
import pygame
from set_up import *

pygame.init()

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Chess")

clock = pygame.time.Clock()

piece_font = pygame.font.SysFont("Segoe UI Symbol", 72)
coordinate_font = pygame.font.SysFont("Segoe UI Symbol", 18)


def draw_chess_board():
    for row in range(8):
        for col in range(8):
            if (row + col) % 2 == 0:
                color = LIGHT_SQUARE
            else:
                color = DARK_SQUARE

            pygame.draw.rect(
                screen,
                color,
                (
                    col * SQUARE_SIZE,
                    row * SQUARE_SIZE,
                    SQUARE_SIZE,
                    SQUARE_SIZE
                )
            )


def draw_chess_pieces():
    for row in range(8):
        for col in range(8):
            piece = board[row][col]

            if piece == ".":
                continue

            symbol = piece_conversion.get(piece, "")

            if piece.isupper():
                text_color = WHITE_PIECE
            else:
                text_color = BLACK_PIECE

            text = piece_font.render(
                symbol,
                True,
                text_color
            )

            x = col * SQUARE_SIZE + SQUARE_SIZE // 2
            y = row * SQUARE_SIZE + SQUARE_SIZE // 2

            text_rect = text.get_rect(
                center=(x, y)
            )

            screen.blit(text, text_rect)


def draw_coordinates():
    files = "abcdefgh"

    for col in range(8):
        letter = coordinate_font.render(
            files[col],
            True,
            (0, 0, 0)
        )

        screen.blit(
            letter,
            (
                col * SQUARE_SIZE + 5,
                BOARD_SIZE - 23
            )
        )

    for row in range(8):
        number = coordinate_font.render(
            str(8 - row),
            True,
            (0, 0, 0)
        )

        screen.blit(
            number,
            (
                5,
                row * SQUARE_SIZE + 5
            )
        )


def draw_chess_game():
    draw_chess_board()
    draw_chess_pieces()
    draw_coordinates()


HIGHLIGHT = (246, 246, 105)   # selected square
LEGAL_DOT = (20, 85, 30)      # quiet legal move
CAPTURE = (180, 50, 50)       # capture / en passant


def draw_highlight(row, col, color):
    pygame.draw.rect(
        screen, color,
        (col * SQUARE_SIZE, row * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE)
    )


def draw_legal_marks(legal_ends):
    for move in legal_ends:
        r, c = int(move[0]), int(move[1])
        cx = c * SQUARE_SIZE + SQUARE_SIZE // 2
        cy = r * SQUARE_SIZE + SQUARE_SIZE // 2
        if move[2:4] in ("Xx", "Ep"):
            pygame.draw.circle(screen, CAPTURE, (cx, cy), 18, 4)
        else:
            pygame.draw.circle(screen, LEGAL_DOT, (cx, cy), 12)


sidebar_title_font = pygame.font.SysFont("Segoe UI", 15)
sidebar_label_font = pygame.font.SysFont("Segoe UI", 14)
sidebar_value_font = pygame.font.SysFont("Segoe UI", 26, bold=True)
sidebar_small_font = pygame.font.SysFont("Segoe UI", 16)


def _format_eval(score):
    if score is None:
        return "—"
    if abs(score) >= 9000:
        return "Mate"
    return f"{score:+.2f}"


def _sidebar_block(x, y, width, label, value, sub=None):
    pygame.draw.rect(screen, SIDEBAR_PANEL, (x, y, width, 92 if sub else 78), border_radius=8)
    label_s = sidebar_label_font.render(label, True, SIDEBAR_MUTED)
    screen.blit(label_s, (x + 12, y + 10))
    value_s = sidebar_value_font.render(str(value), True, SIDEBAR_TEXT)
    screen.blit(value_s, (x + 12, y + 32))
    if sub:
        sub_s = sidebar_small_font.render(sub, True, SIDEBAR_ACCENT)
        screen.blit(sub_s, (x + 12, y + 66))
    return y + (102 if sub else 88)


def draw_sidebar(winner=None):
    x0 = BOARD_SIZE
    pygame.draw.rect(screen, SIDEBAR_BG, (x0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT))
    pygame.draw.line(screen, (70, 70, 78), (x0, 0), (x0, SCREEN_HEIGHT), 2)

    pad = 16
    x = x0 + pad
    width = SIDEBAR_WIDTH - pad * 2
    y = 18

    title = sidebar_title_font.render("GAME INFO", True, SIDEBAR_ACCENT)
    screen.blit(title, (x, y))
    y += 32

    if winner == "W":
        turn_text = "Game over"
        turn_sub = "White wins"
    elif winner == "B":
        turn_text = "Game over"
        turn_sub = "Black wins"
    elif winner == "S":
        turn_text = "Game over"
        turn_sub = "Stalemate"
    elif winner == "D":
        turn_text = "Game over"
        turn_sub = "Draw"
    else:
        turn_text = "White" if engine.White_Turn else "Black"
        if is_human_turn(engine.White_Turn):
            turn_sub = "Your move"
        else:
            turn_sub = "Engine thinking"
    y = _sidebar_block(x, y, width, "TURN", turn_text, turn_sub)

    y = _sidebar_block(
        x, y, width, "ENGINE",
        str(ENGINE_RATING),
        f"Depth {ENGINE_DEPTH}  (max {MAX_ENGINE_DEPTH})",
    )

    search = engine.LAST_SEARCH_SCORE
    eval_sub = "Engine search" if search is not None else "After the engine moves"
    y = _sidebar_block(x, y, width, "EVALUATION", _format_eval(search), eval_sub)

    white_m, black_m = material_count(board)
    diff = white_m - black_m
    if diff > 0:
        mat_sub = f"White +{diff}"
    elif diff < 0:
        mat_sub = f"Black +{abs(diff)}"
    else:
        mat_sub = "Equal"
    y = _sidebar_block(x, y, width, "MATERIAL", f"{white_m} – {black_m}", mat_sub)


def draw_game_over(winner):
    if winner == "S":
        text = "Stalemate"
    elif winner == "D":
        text = "Draw"
    elif winner == "W":
        text = "White wins"
    else:
        text = "Black wins"
    font = pygame.font.SysFont("dejavusans", 48, bold=True)
    label = font.render(text, True, (255, 255, 255))
    rect = label.get_rect(center=(BOARD_SIZE // 2, BOARD_SIZE // 2))
    bg = pygame.Rect(0, 0, rect.width + 40, rect.height + 20)
    bg.center = rect.center
    pygame.draw.rect(screen, (0, 0, 0), bg)
    screen.blit(label, rect)
