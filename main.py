from engine import *
from display import *
import engine
import time
from game_history import *


def setup_game():
    global GAME_MODE, PLAYER_IS_WHITE, PLAYER_IS_BLACK, ENGINE_DEPTH, MAX_ENGINE_DEPTH, WHITE_PLAYER, BLACK_PLAYER
    global LAST_SEARCH_SCORE

    print("\n=== CHESS ===")
    print("1) Player vs AI")
    print("2) AI vs AI")
    print("3) Player vs Player")
    print("4) Check Game History")
    choice = ""
    while choice not in ("1", "2", "3", "4"):
        choice = input("Choose mode (1-4): ").strip()

    if choice == "1":
        GAME_MODE = "pva"
        color = ""
        while color not in ("w", "b", "white", "black"):
            color = input("Play as White or Black? (w/b): ").strip().lower()
        PLAYER_IS_WHITE = color in ("w", "white")
        PLAYER_IS_BLACK = not PLAYER_IS_WHITE
        if color == "w":
            WHITE_PLAYER = input("Name of the white player: ")
            BLACK_PLAYER = "Hamptaro AI"
        elif color == "b":
            BLACK_PLAYER = input("Name of the black player: ")
            WHITE_PLAYER = "Hamptaro AI"
        depth = input(f"AI depth [{ENGINE_DEPTH}]: ").strip()
        if depth.isdigit() and int(depth) > 0:
            ENGINE_DEPTH = int(depth)
        max_depth = input(f"AI max depth [{MAX_ENGINE_DEPTH}]: ").strip()
        if max_depth.isdigit() and int(max_depth) >= int(depth or ENGINE_DEPTH):
            MAX_ENGINE_DEPTH = int(max_depth)
        side = "White" if PLAYER_IS_WHITE else "Black"
        print(f"Player vs AI — you are {side}, AI depth {ENGINE_DEPTH}")
    elif choice == "2":
        GAME_MODE = "ava"
        WHITE_PLAYER = "Hamptaro AI"
        BLACK_PLAYER = "Hamptaro AI"
        PLAYER_IS_WHITE = False
        PLAYER_IS_BLACK = False
        depth = input(f"AI depth [{ENGINE_DEPTH}]: ").strip()
        if depth.isdigit() and int(depth) > 0:
            ENGINE_DEPTH = int(depth)
        max_depth = input(f"AI max depth [{MAX_ENGINE_DEPTH}]: ").strip()
        if max_depth.isdigit() and int(max_depth) >= int(depth or ENGINE_DEPTH):
            MAX_ENGINE_DEPTH = int(max_depth)
        print(f"AI vs AI — depth {ENGINE_DEPTH}")
    elif choice == "3":
        WHITE_PLAYER = input("Name of the white player: ")
        BLACK_PLAYER = input("Name of the black player: ")
        GAME_MODE = "pvp"
        PLAYER_IS_WHITE = True
        PLAYER_IS_BLACK = True
        print("Player vs Player")
    elif choice == "4":
        global current_game
        current_game = find_game(load_game_history())
    if choice != "4":
        game_history.append([[row[:] for row in board]])
        date_of_game = str(date.today())
        game_history.append([WHITE_PLAYER, BLACK_PLAYER, date_of_game])
        current_game = None

    game_rep_history.clear()
    game_rep_history.append(hash_position(board, True, current_castling()))
    LAST_SEARCH_SCORE = None


def set_white_turn(value):
    global White_Turn
    White_Turn = value
    engine.White_Turn = value


def apply_game_end_eval(winner):
    if winner in ("D", "S"):
        engine.LAST_SEARCH_SCORE = DRAW_SCORE
    elif winner == "W":
        engine.LAST_SEARCH_SCORE = 10000
    elif winner == "B":
        engine.LAST_SEARCH_SCORE = -10000


def play_ai_move():
    global White_Turn, LAST_SEARCH_SCORE

    ended = game_result(board, White_Turn)

    if ended is not None:
        apply_game_end_eval(ended)
        return ended

    start = time.time()

    score, best = choose_ai_move(
        board,
        White_Turn,
        ENGINE_DEPTH,
        maximum_depth=MAX_ENGINE_DEPTH,
    )

    LAST_SEARCH_SCORE = score
    engine.LAST_SEARCH_SCORE = score

    if best is None:
        best = pick_legal_move(White_Turn, board)

        if best is None:
            return game_result(board, White_Turn)

    game_history.append([best[0], best[1][0] + best[1][1]])

    print(score)
    print(best)

    end = time.time()
    print(end - start)

    start, dest = best[0], best[1]

    piece = board[int(start[0])][int(start[1])]

    pos_hash = hash_position(
        board,
        White_Turn,
        current_castling()
    )

    child_hash, _undo = make_move_engine(
        start,
        dest,
        board,
        piece,
        pos_hash
    )

    set_white_turn(not White_Turn)

    game_rep_history.append(
        hash_position(
            board,
            White_Turn,
            current_castling()
        )
    )

    tt_save()

    winner = game_result(board, White_Turn)

    apply_game_end_eval(winner)

    return winner


def square_key(row, col):
    return str(row) + str(col)


def find_dest(legal_ends, row, col):
    prefix = square_key(row, col)

    for move in legal_ends:
        if move[:2] == prefix:
            return move

    return None


def pixel_to_square(pos):
    x, y = pos

    col = x // SQUARE_SIZE
    row = y // SQUARE_SIZE

    if 0 <= row < 8 and 0 <= col < 8:
        return row, col

    return None


def handle_click(row, col, selected, legal_ends, winner):
    global White_Turn

    if winner is not None:
        return selected, legal_ends, winner

    if not is_human_turn(White_Turn):
        return selected, legal_ends, winner

    key = square_key(row, col)

    possible = determine_possible_moves(
        White_Turn,
        board
    )

    if selected is not None:
        dest = find_dest(
            legal_ends,
            row,
            col
        )

        if dest is not None:
            sr, sc = selected

            start = square_key(
                sr,
                sc
            )

            piece = board[sr][sc]

            promo = None

            if dest[2:4] == "Pw":
                promo = "Q"

            elif dest[2:4] == "Pb":
                promo = "q"

            result = make_move(
                start,
                dest[:2],
                legal_ends,
                piece,
                promo
            )

            if result is None:
                set_white_turn(
                    not White_Turn
                )

                game_rep_history.append(
                    hash_position(
                        board,
                        White_Turn,
                        current_castling()
                    )
                )

                winner = game_result(
                    board,
                    White_Turn
                )

                apply_game_end_eval(winner)

                return None, [], winner

        if key in possible:
            return (
                (row, col),
                possible[key],
                winner
            )

        return None, [], winner

    if key in possible:
        return (
            (row, col),
            possible[key],
            winner
        )

    return None, [], winner


def main():
    History_White_Turn = True
    game_move_number = 1
    running = True

    selected = None
    legal_ends = []
    winner = None

    while running:

        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                maybe_tt_save(force=True)
                running = False

            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and current_game is None
            ):
                sq = pixel_to_square(event.pos)

                if sq is not None:
                    selected, legal_ends, winner = handle_click(
                        sq[0],
                        sq[1],
                        selected,
                        legal_ends,
                        winner
                    )

            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 3
                and current_game is None
            ):
                selected = None
                legal_ends = []

            if (
                event.type == pygame.KEYDOWN
                and event.key == pygame.K_SPACE
                and current_game is not None
            ):
                try:
                    move_piece_game_history(current_game[game_move_number + 1][0], current_game[game_move_number + 1][1], History_White_Turn)
                except IndexError:
                    print("End of Game")
                History_White_Turn = not History_White_Turn
                game_move_number += 1

        screen.fill((30, 30, 30))

        draw_chess_board()

        if selected is not None and current_game is None:
            draw_highlight(
                selected[0],
                selected[1],
                HIGHLIGHT
            )

        draw_legal_marks(legal_ends)
        draw_chess_pieces()
        draw_coordinates()
        draw_sidebar(winner)

        pygame.display.flip()

        if winner is not None:
            draw_game_over(winner)

        pygame.display.flip()

        if (
            winner is None
            and not is_human_turn(White_Turn)
            and current_game is None
        ):
            winner = play_ai_move()

        clock.tick(60)

    if current_game is None:
        save_game_history()
    pygame.quit()


if __name__ == "__main__":
    setup_game()
    if current_game is not None:
        board = current_game[0]
    main()
