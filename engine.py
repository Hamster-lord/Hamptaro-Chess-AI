import random
import json
import pickle
from pathlib import Path
from datetime import date
import os
from game_history import *

Games_Against_Other_AI_Score = [2150, 2300, 2300, 2450, 2250]
print("The approximate rating of this AI is: " + str(
    sum(Games_Against_Other_AI_Score) / len(Games_Against_Other_AI_Score)))
ENGINE_RATING = int(sum(Games_Against_Other_AI_Score) / len(Games_Against_Other_AI_Score))
LAST_SEARCH_SCORE = None
WHITE_PLAYER = None
BLACK_PLAYER = None
game_history = []
current_game = None
path = Path(__file__).resolve().parent / "save.json"
pkl_path = path.with_suffix(".pkl")

rng = random.Random("HAMSTER")
PIECES = ["P", "N", "B", "R", "Q", "K", "p", "n", "b", "r", "q", "k"]


def rand64():
    return rng.getrandbits(64)


zobrist_pieces = {
    p: [[rand64() for _ in range(8)] for _ in range(8)]
    for p in PIECES
}
zobrist_side = rand64()
zobrist_castle = [rand64() for _ in range(4)]
zobrist_ep = [rand64() for _ in range(8)]


def hash_toggle_ep(h, ep):
    if ep is not None:
        h ^= zobrist_ep[ep[1]]
    return h


def hash_position(board, white_turn, castling):
    h = 0
    for r in range(8):
        for c in range(8):
            piece = board[r][c]
            if piece != ".":
                h ^= zobrist_pieces[piece][r][c]

    if not white_turn:
        h ^= zobrist_side

    for i, flag in enumerate(castling):
        if flag:
            h ^= zobrist_castle[i]
    h = hash_toggle_ep(h, EP_SQUARE)
    return h


def hash_quiet_move(h, piece, sr, sc, er, ec):
    h ^= zobrist_pieces[piece][sr][sc]
    h ^= zobrist_pieces[piece][er][ec]
    h ^= zobrist_side
    return h


def hash_capture(h, piece, captured, sr, sc, er, ec):
    h ^= zobrist_pieces[piece][sr][sc]
    h ^= zobrist_pieces[captured][er][ec]
    h ^= zobrist_pieces[piece][er][ec]
    h ^= zobrist_side
    return h


def hash_promo(h, pawn, promo, sr, sc, er, ec, captured=None):
    h ^= zobrist_pieces[pawn][sr][sc]
    if captured is not None:
        h ^= zobrist_pieces[captured][er][ec]
    h ^= zobrist_pieces[promo][er][ec]
    h ^= zobrist_side
    return h


def hash_ep_capture(h, piece, captured, sr, sc, er, ec, cap_r, cap_c):
    h ^= zobrist_pieces[piece][sr][sc]
    h ^= zobrist_pieces[captured][cap_r][cap_c]
    h ^= zobrist_pieces[piece][er][ec]
    h ^= zobrist_side
    return h


def hash_set_castle(h, index, old, new):
    if old != new:
        h ^= zobrist_castle[index]
    return h


def current_castling():
    return [White_Castle_Right, White_Castle_Left, Black_Castle_Right, Black_Castle_Left]


TT = {}
TT_EXACT = 0
TT_LOWER = 1
TT_UPPER = 2
TT_MAX_SAVE = 40000
TT_VERSION = 1
TT_ZOBRIST_ID = "HAMSTER"

KILLERS = {}
HISTORY = {}

KNIGHT_DIRS = ((1, 2), (2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1), (-1, 2), (-2, 1))
KING_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
ROOK_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
BISHOP_DIRS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
QUEEN_DIRS = ROOK_DIRS + BISHOP_DIRS


def tt_clear():
    TT.clear()


def maybe_tt_save(force=False):
    tt_save()


def tt_store(pos_hash, depth, score, flag, best_move):
    if score != score or score in (float("inf"), float("-inf")):
        return
    entry = TT.get(pos_hash)
    if entry is None or depth >= entry[0]:
        TT[pos_hash] = (depth, score, flag, best_move)


def tt_probe(pos_hash, depth, alpha, beta):
    entry = TT.get(pos_hash)
    if entry is None:
        return False, None, None

    d, score, flag, best_move = entry
    if d < depth:
        return False, None, best_move

    if flag == TT_EXACT:
        return True, score, best_move
    if flag == TT_LOWER and score >= beta:
        return True, score, best_move
    if flag == TT_UPPER and score <= alpha:
        return True, score, best_move
    return False, None, best_move


def tt_move_exists(board, turn, tt_move):
    if tt_move is None:
        return False
    try:
        start, end = tt_move[0], tt_move[1]
        sr, sc = int(start[0]), int(start[1])
        piece = board[sr][sc]
    except (TypeError, ValueError, IndexError):
        return False
    if piece == ".":
        return False
    if turn and piece.islower():
        return False
    if (not turn) and piece.isupper():
        return False
    return end in generate_pseudo_moves(turn, board).get(start, [])


def _tt_entry_ok(score, depth, flag, best_move):
    if score != score or score in (float("inf"), float("-inf")):
        return False
    if not isinstance(depth, int) or depth < -64 or depth > 64:
        return False
    if flag not in (TT_EXACT, TT_LOWER, TT_UPPER):
        return False
    if best_move is not None:
        if not isinstance(best_move, (list, tuple)) or len(best_move) != 2:
            return False
        if not isinstance(best_move[0], str) or not isinstance(best_move[1], str):
            return False
    return True


def tt_save():
    if not TT:
        return
    data = TT
    if len(TT) > TT_MAX_SAVE:
        data = dict(sorted(TT.items(), key=lambda kv: kv[1][0], reverse=True)[:TT_MAX_SAVE])
    try:
        with pkl_path.open("wb") as f:
            pickle.dump((TT_VERSION, TT_ZOBRIST_ID, data), f, pickle.HIGHEST_PROTOCOL)
    except OSError:
        pass


def _tt_load_list(raw):
    loaded = 0
    for item in raw:
        if not isinstance(item, list) or len(item) < 5:
            continue
        try:
            key = int(item[0])
            depth = int(item[1])
            score = float(item[2])
            flag = int(item[3])
            best_move = item[4]
        except (TypeError, ValueError):
            continue
        if not _tt_entry_ok(score, depth, flag, best_move):
            continue
        TT[key] = (depth, score, flag, best_move)
        loaded += 1
    return loaded


def _tt_load_dict(raw):
    loaded = 0
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        try:
            key = int(v.get("key", k))
            depth = int(v["depth"])
            score = float(v["score"])
            flag = int(v["flag"])
            best_move = v.get("best_move")
        except (KeyError, TypeError, ValueError):
            continue
        if not _tt_entry_ok(score, depth, flag, best_move):
            continue
        TT[key] = (depth, score, flag, best_move)
        loaded += 1
    return loaded


def tt_load():
    if pkl_path.exists():
        try:
            with pkl_path.open("rb") as f:
                ver, zid, data = pickle.load(f)
            if zid == TT_ZOBRIST_ID and isinstance(data, dict):
                TT.clear()
                TT.update(data)
                return
        except (OSError, pickle.UnpicklingError, ValueError, TypeError):
            pass
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict):
        return
    if data.get("zid") not in (None, TT_ZOBRIST_ID):
        return
    raw = data.get("tt")
    TT.clear()
    if isinstance(raw, list):
        _tt_load_list(raw)
    elif isinstance(raw, dict):
        _tt_load_dict(raw)


tt_load()

board = [
    ["r", "n", "b", "q", "k", "b", "n", "r"],
    ["p", "p", "p", "p", "p", "p", "p", "p"],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    [".", ".", ".", ".", ".", ".", ".", "."],
    ["P", "P", "P", "P", "P", "P", "P", "P"],
    ["R", "N", "B", "Q", "K", "B", "N", "R"]
]
PAWN_TABLE = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [50, 50, 50, 50, 50, 50, 50, 50],
    [10, 10, 20, 40, 40, 20, 10, 10],
    [5, 5, 10, 40, 40, 10, 5, 5],
    [0, 0, 20, 40, 40, -10, 0, 0],
    [5, 10, 15, 5, 5, -10, 10, 5],
    [5, 10, 10, -20, -20, 10, 10, 5],
    [0, 0, 0, 0, 0, 0, 0, 0]
]
KNIGHT_TABLE = [
    [-50, -40, -30, -30, -30, -30, -40, -50],
    [-40, -20, 0, 0, 0, 0, -20, -40],
    [-30, 5, 15, 20, 20, 15, 5, -30],
    [-30, 10, 20, 30, 30, 20, 10, -30],
    [-30, 5, 20, 30, 30, 20, 5, -30],
    [-30, 5, 15, 20, 20, 15, 5, -30],
    [-40, -20, -5, -25, -25, -5, -20, -40],
    [-50, -40, -30, -30, -30, -30, -40, -50],
]
BISHOP_TABLE = [
    [-20, -10, -10, -10, -10, -10, -10, -20],
    [-10, 5, 0, 0, 0, 0, 5, -10],
    [-10, 10, 10, 10, 10, 10, 10, -10],
    [-10, 0, 10, 10, 10, 10, 0, -10],
    [-10, 5, 5, 10, 10, 5, 5, -10],
    [-10, 0, 5, 10, 10, 5, 0, -10],
    [-10, 10, 0, 0, 0, 0, 10, -10],
    [-20, -10, -20, -10, -20, -10, -10, -20]
]
ROOK_TABLE = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [5, 10, 10, 10, 10, 10, 10, 5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [0, 5, 5, 10, 10, 5, 5, 0]
]
QUEEN_TABLE = [
    [-20, -10, -10, -5, -5, -10, -10, -20],
    [-10, 0, 0, 0, 0, 0, 0, -10],
    [-10, 0, 5, 5, 5, 5, 0, -10],
    [-5, 0, 5, 5, 5, 5, 0, -5],
    [0, 0, 5, 5, 5, 5, 0, -5],
    [-10, 5, 5, 5, 5, 5, 0, -10],
    [-10, 0, 5, 0, 0, 0, 0, -10],
    [-20, -10, -10, -5, -5, -10, -10, -20]
]
KING_TABLE = [
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-20, -30, -30, -40, -40, -30, -30, -20],
    [-10, -20, -20, -20, -20, -20, -20, -10],
    [20, 20, -10, -10, -10, -10, 20, 20],
    [20, 30, 10, 0, 0, 10, 30, 20]
]
KING_ENDTABLE = [
    [-50, -30, -30, -30, -30, -30, -30, -50],
    [-30, -10, 0, 0, 0, 0, -10, -30],
    [-30, 0, 20, 30, 30, 20, 0, -30],
    [-30, 0, 30, 40, 40, 30, 0, -30],
    [-30, 0, 30, 40, 40, 30, 0, -30],
    [-30, 0, 20, 30, 30, 20, 0, -30],
    [-30, -10, 0, 0, 0, 0, -10, -30],
    [-50, -30, -30, -30, -30, -30, -30, -50]
]
BLACK_PAWN_TABLE = PAWN_TABLE[::-1]
BLACK_KNIGHT_TABLE = KNIGHT_TABLE[::-1]
BLACK_BISHOP_TABLE = BISHOP_TABLE[::-1]
BLACK_ROOK_TABLE = ROOK_TABLE[::-1]
BLACK_QUEEN_TABLE = QUEEN_TABLE[::-1]
BLACK_KING_TABLE = KING_TABLE[::-1]
BLACK_KING_ENDTABLE = KING_ENDTABLE[::-1]
WHITE_PST = {
    "P": PAWN_TABLE, "N": KNIGHT_TABLE, "B": BISHOP_TABLE,
    "R": ROOK_TABLE, "Q": QUEEN_TABLE,
}
BLACK_PST = {
    "p": BLACK_PAWN_TABLE, "n": BLACK_KNIGHT_TABLE, "b": BLACK_BISHOP_TABLE,
    "r": BLACK_ROOK_TABLE, "q": BLACK_QUEEN_TABLE,
}
BEST_ENGINE_MOVE = ""
VARIATION_EVAL = {}
PIECE_VALUES = {
    "p": 100, "n": 290, "b": 310, "r": 500, "q": 900, "k": 10000,
    "P": 100, "N": 290, "B": 310, "R": 500, "Q": 900, "K": 10000,
}
Black_Castle = False
White_Castle = False
White_Castle_Right = True
White_Castle_Left = True
Black_Castle_Right = True
Black_Castle_Left = True
EP_SQUARE = None

GAME_MODE = "pva"
PLAYER_IS_WHITE = True
PLAYER_IS_BLACK = False
ENGINE_DEPTH = 6
MAX_ENGINE_DEPTH = 8

game_rep_history = []


if not os.path.exists("games.json"):
    with open("games.json", "w") as file:
        json.dump([[board], [None, None, "0000-00-00"]], file)


def save_game_history():
    previous_games = load_game_history()
    with open("games.json", "w") as file:
        json.dump([game_history] + previous_games, file)


def load_game_history():
    with open("games.json", "r") as file:
        data = json.load(file)
    return data


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

    game_rep_history.clear()
    game_rep_history.append(hash_position(board, True, current_castling()))
    LAST_SEARCH_SCORE = None


def is_human_turn(white_turn):
    if white_turn:
        return PLAYER_IS_WHITE
    return PLAYER_IS_BLACK


def find_king(board, white):
    target = "K" if white else "k"
    for r in range(8):
        for c in range(8):
            if board[r][c] == target:
                return r, c
    return None


def is_square_attacked(board, row, col, by_white):
    if by_white:
        for dc in (-1, 1):
            r, c = row + 1, col + dc
            if 0 <= r < 8 and 0 <= c < 8 and board[r][c] == "P":
                return True
        knight, king = "N", "K"
        rook_q, bishop_q = "RQ", "BQ"
    else:
        for dc in (-1, 1):
            r, c = row - 1, col + dc
            if 0 <= r < 8 and 0 <= c < 8 and board[r][c] == "p":
                return True
        knight, king = "n", "k"
        rook_q, bishop_q = "rq", "bq"

    for a, b in ((1, 2), (2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1), (-1, 2), (-2, 1)):
        r, c = row + a, col + b
        if 0 <= r < 8 and 0 <= c < 8 and board[r][c] == knight:
            return True

    for a in range(-1, 2):
        for b in range(-1, 2):
            if a == 0 and b == 0:
                continue
            r, c = row + a, col + b
            if 0 <= r < 8 and 0 <= c < 8 and board[r][c] == king:
                return True

    def ray(dr, dc, pieces):
        r, c = row + dr, col + dc
        while 0 <= r < 8 and 0 <= c < 8:
            p = board[r][c]
            if p != ".":
                return p in pieces
            r += dr
            c += dc
        return False

    if ray(1, 0, rook_q) or ray(-1, 0, rook_q) or ray(0, 1, rook_q) or ray(0, -1, rook_q):
        return True
    if ray(1, 1, bishop_q) or ray(1, -1, bishop_q) or ray(-1, 1, bishop_q) or ray(-1, -1, bishop_q):
        return True
    return False


def in_check(board, white):
    pos = find_king(board, white)
    if pos is None:
        return True
    return is_square_attacked(board, pos[0], pos[1], by_white=not white)


def lose_castling_from_move(piece, sr, sc, er, ec):
    global White_Castle_Right, White_Castle_Left, Black_Castle_Right, Black_Castle_Left
    if piece == "K":
        White_Castle_Right = False
        White_Castle_Left = False
    elif piece == "k":
        Black_Castle_Right = False
        Black_Castle_Left = False
    if piece == "R" and (sr, sc) == (7, 7):
        White_Castle_Right = False
    if piece == "R" and (sr, sc) == (7, 0):
        White_Castle_Left = False
    if piece == "r" and (sr, sc) == (0, 7):
        Black_Castle_Right = False
    if piece == "r" and (sr, sc) == (0, 0):
        Black_Castle_Left = False
    if (er, ec) == (7, 7):
        White_Castle_Right = False
    if (er, ec) == (7, 0):
        White_Castle_Left = False
    if (er, ec) == (0, 7):
        Black_Castle_Right = False
    if (er, ec) == (0, 0):
        Black_Castle_Left = False


def apply_rights_hash(h, old_rights):
    new_rights = current_castling()
    for i in range(4):
        h = hash_set_castle(h, i, old_rights[i], new_rights[i])
    return h


def set_ep_after_move(piece, sr, sc, er):
    global EP_SQUARE
    if piece == "P" and sr == 6 and er == 4:
        EP_SQUARE = (5, sc)
    elif piece == "p" and sr == 1 and er == 3:
        EP_SQUARE = (2, sc)
    else:
        EP_SQUARE = None


def after_human_move(piece, start, end):
    sr, sc = int(start[0]), int(start[1])
    er, ec = int(end[0]), int(end[1])
    lose_castling_from_move(piece, sr, sc, er, ec)
    set_ep_after_move(piece, sr, sc, er)


KING_CENTER_MAX_PIECES = 4


def queens_alive(board):
    wq = bq = False
    for r in range(8):
        for c in range(8):
            if board[r][c] == "Q":
                wq = True
            elif board[r][c] == "q":
                bq = True
    return wq, bq


def development_terms(board, wq=None, bq=None):
    score = 0
    if wq is None or bq is None:
        wq, bq = queens_alive(board)
    if wq and bq:
        if board[6][2] != "P":
            score += 12
        if board[6][3] != "P":
            score += 20
        if board[6][4] != "P":
            score += 20
        if board[6][5] != "P":
            score += 10

        if board[1][2] != "p":
            score -= 12
        if board[1][3] != "p":
            score -= 20
        if board[1][4] != "p":
            score -= 20
        if board[1][5] != "p":
            score -= 10

    if board[6][2] == "P" and board[7][1] != "N":
        score -= 10
    if board[6][3] == "P" and board[7][2] != "B":
        score -= 10
    if board[6][4] == "P" and board[7][6] != "N":
        score -= 10
    if board[6][5] == "P" and board[7][5] != "B":
        score -= 10
    if board[1][2] == "p" and board[0][1] != "n":
        score += 10
    if board[1][3] == "p" and board[0][2] != "b":
        score += 10
    if board[1][4] == "p" and board[0][6] != "n":
        score += 10
    if board[1][5] == "p" and board[0][5] != "b":
        score += 10
    Black_Development = 0
    White_Development = 0

    if board[0][1] != "n":
        Black_Development += 1
    if board[0][6] != "n":
        Black_Development += 1
    if board[0][2] != "b":
        Black_Development += 1
    if board[0][5] != "b":
        Black_Development += 1
    if board[7][1] != "N":
        White_Development += 1
    if board[7][6] != "N":
        White_Development += 1
    if board[7][2] != "B":
        White_Development += 1
    if board[7][5] != "B":
        White_Development += 1
    if board[0][3] != "Q":
        score -= White_Development * 20
    if board[7][3] != "Q":
        score += Black_Development * 20
    score += White_Development * 15
    score -= Black_Development * 15

    if board[5][2] == "N":
        score += 14
    if board[5][5] == "N":
        score += 14
    if board[2][2] == "n":
        score -= 14
    if board[2][5] == "n":
        score -= 14

    if board[7][1] == "N" and (board[5][2] == "." or board[5][3] != "P"):
        score -= 6
    if board[7][6] == "N" and (board[5][5] == "." or board[5][4] != "P"):
        score -= 6
    if board[0][1] == "n" and (board[2][2] == "." or board[2][3] != "p"):
        score += 6
    if board[0][6] == "n" and (board[2][5] == "." or board[2][4] != "p"):
        score += 6

    if board[7][2] == "B":
        if board[6][3] == "N":
            score -= 22
        if board[5][3] == "N":
            score -= 12
    if board[7][5] == "B":
        if board[6][4] == "N":
            score -= 22
        if board[5][4] == "N":
            score -= 12

    if board[0][2] == "b":
        if board[1][3] == "n":
            score += 22
        if board[2][3] == "n":
            score += 12
    if board[0][5] == "b":
        if board[1][4] == "n":
            score += 22
        if board[2][4] == "n":
            score += 12

    if board[5][2] == "N":
        if board[6][3] == "P" and board[6][4] == "P" and board[6][2] == "P" and board[6][5] == "P":
            score -= 25
    if board[5][5] == "N":
        if board[6][3] == "P" and board[6][4] == "P" and board[6][2] == "P" and board[6][5] == "P":
            score -= 25
    if board[2][2] == "n":
        if board[1][3] == "p" and board[1][4] == "p" and board[1][2] == "p" and board[1][5] == "p":
            score += 25
    if board[2][5] == "n":
        if board[1][3] == "p" and board[1][4] == "p" and board[1][2] == "p" and board[1][5] == "p":
            score += 25

    if board[5][3] == "Q" and board[7][5] == "B":
        score -= 40

    if board[2][3] == "q" and board[0][5] == "b":
        score += 40

    for c in (0, 7):
        if board[7][c] == "N":
            score -= 10
        if board[0][c] == "n":
            score += 10
    for c in (0, 7):
        if board[5][c] == "N":
            score -= 9
        if board[2][c] == "n":
            score += 9
    return score


def material_count(board):
    values = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9,
              "p": 1, "n": 3, "b": 3, "r": 5, "q": 9}
    white = black = 0
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p in values:
                if p.isupper():
                    white += values[p]
                else:
                    black += values[p]
    return white, black


DRAW_SCORE = 0.0


def is_insufficient_material(board):
    white = []
    black = []
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p in (".", "K", "k"):
                continue
            if p in ("P", "p", "R", "r", "Q", "q"):
                return False
            if p.isupper():
                white.append((p, r, c))
            else:
                black.append((p, r, c))
    n = len(white) + len(black)
    if n == 0:
        return True
    if n == 1:
        p = (white[0][0] if white else black[0][0])
        return p in ("N", "n", "B", "b")
    if len(white) == 1 and len(black) == 1:
        pw, rw, cw = white[0]
        pb, rb, cb = black[0]
        if pw in ("B", "b") and pb in ("B", "b"):
            return (rw + cw) % 2 == (rb + cb) % 2
    return False


def evaluation(board):
    if is_insufficient_material(board):
        return DRAW_SCORE
    score = 0
    wq = False
    bq = False
    fighters = 0
    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p == "." or p in ("K", "k", "P", "p"):
                continue
            fighters += 1
            if p == "Q":
                wq = True
            elif p == "q":
                bq = True
    king_endgame = fighters <= KING_CENTER_MAX_PIECES

    for r, c in ((3, 3), (3, 4), (4, 3), (4, 4)):
        p = board[r][c]
        if p == "P":
            score += 50
        elif p == "p":
            score -= 50

    score += development_terms(board, wq, bq)

    if White_Castle:
        score += 40
    if Black_Castle:
        score -= 40

    for r in range(8):
        for c in range(8):
            piece = board[r][c]
            if piece == ".":
                continue
            if piece.isupper():
                score += PIECE_VALUES[piece]
                if piece == "K":
                    score += (KING_ENDTABLE if king_endgame else KING_TABLE)[r][c]
                else:
                    score += WHITE_PST[piece][r][c]
            else:
                score -= PIECE_VALUES[piece]
                if piece == "k":
                    score -= (BLACK_KING_ENDTABLE if king_endgame else BLACK_KING_TABLE)[r][c]
                else:
                    score -= BLACK_PST[piece][r][c]
    return score / 100


def mate_or_stale(board, turn, ply):
    if in_check(board, turn):
        return (-10000 + ply) if turn else (10000 - ply)
    return DRAW_SCORE


def order_moves(move_list, engine_board, tt_move, killers):
    def pri(m):
        start, end = m
        sr, sc = int(start[0]), int(start[1])
        er, ec = int(end[0]), int(end[1])
        piece = engine_board[sr][sc]
        flag = end[2:4]
        key = (start, end)
        if tt_move is not None and start == tt_move[0] and end == tt_move[1]:
            return 2_000_000
        if flag == "Xx":
            victim = engine_board[er][ec]
            return 1_000_000 + PIECE_VALUES.get(victim, 0) * 10 - PIECE_VALUES.get(piece, 0)
        if flag == "Ep":
            return 1_000_000 + PIECE_VALUES["p"] * 10 - PIECE_VALUES.get(piece, 0)
        if flag in ("Pw", "Pb"):
            bonus = 900_000
            if engine_board[er][ec] != ".":
                bonus += PIECE_VALUES.get(engine_board[er][ec], 0) * 10
            return bonus
        for i, k in enumerate(killers):
            if k == key:
                return 800_000 - i * 1000
        val = HISTORY.get(key, 0)
        if piece == "N" and sr == 7:
            val += 30
        elif piece == "n" and sr == 0:
            val += 30
        elif piece == "B" and sr == 7:
            val += 35
        elif piece == "b" and sr == 0:
            val += 35
        if piece == "N" and (er, ec) in ((5, 2), (5, 5)):
            val += 50
        elif piece == "n" and (er, ec) in ((2, 2), (2, 5)):
            val += 50
        if piece == "N" and (er, ec) in ((6, 3), (6, 4)):
            val -= 60
        elif piece == "n" and (er, ec) in ((1, 3), (1, 4)):
            val -= 60
        return val

    move_list.sort(key=pri, reverse=True)


def record_cutoff(start, end, is_capture, ply, depth):
    key = (start, end)
    if not is_capture:
        ks = KILLERS.get(ply, [])
        if key not in ks:
            KILLERS[ply] = ([key] + ks)[:2]
    HISTORY[key] = HISTORY.get(key, 0) + max(1, abs(depth))


def pick_legal_move(turn, board):
    possible = determine_possible_moves(turn, board)
    for start, ends in possible.items():
        if ends:
            return [start, ends[0]]
    return None


def _tt_root_entry(engine_board, turn, pos_hash):
    entry = TT.get(pos_hash)
    if entry is None:
        return None
    depth, score, flag, best_move = entry
    if best_move is None or not tt_move_exists(engine_board, turn, best_move):
        return None
    return depth, score, flag, [best_move[0], best_move[1]]


def choose_ai_move(engine_board, turn, max_depth, maximum_depth=0):
    if is_insufficient_material(engine_board):
        return DRAW_SCORE, None
    pos_hash = hash_position(engine_board, turn, current_castling())
    repeats = 0
    for h in game_rep_history:
        if h == pos_hash:
            repeats += 1
    if repeats >= 3:
        return DRAW_SCORE, pick_legal_move(turn, engine_board)
    saved = _tt_root_entry(engine_board, turn, pos_hash)
    if repeats < 2 and saved is not None:
        saved_depth, score, flag, best = saved
        if saved_depth >= max_depth and flag == TT_EXACT:
            return score, best
    return engine(engine_board, turn, max_depth, maximum_depth=maximum_depth)


def engine(engine_board, turn, depth=4, alpha=-float("inf"), beta=float("inf"),
           moves_made=None, pos_hash=None, maximum_depth=0, rep_counts=None):
    if moves_made is None:
        moves_made = []
    ply = len(moves_made)
    if pos_hash is None:
        pos_hash = hash_position(engine_board, turn, current_castling())
    if is_insufficient_material(engine_board):
        return DRAW_SCORE, None
    if rep_counts is None:
        rep_counts = {}
        for h in game_rep_history:
            rep_counts[h] = rep_counts.get(h, 0) + 1
        if not game_rep_history or game_rep_history[-1] != pos_hash:
            rep_counts[pos_hash] = rep_counts.get(pos_hash, 0) + 1

    if ply > 0 and rep_counts.get(pos_hash, 0) >= 2:
        return DRAW_SCORE, None

    orig_alpha = alpha
    in_quiescence = depth < 1
    can_tt = (not in_quiescence) and (rep_counts.get(pos_hash, 0) < 2)
    tt_move = None
    tt_hit, tt_score, tt_move = tt_probe(pos_hash, depth, alpha, beta)
    if can_tt and tt_hit:
        if ply > 0 or tt_move_exists(engine_board, turn, tt_move):
            return tt_score, tt_move

    in_chk = in_check(engine_board, turn)
    possible = generate_pseudo_moves(turn, engine_board)

    if not possible:
        score = mate_or_stale(engine_board, turn, ply)
        if can_tt:
            tt_store(pos_hash, depth, score, TT_EXACT, None)
        return score, None

    q_limit = maximum_depth if maximum_depth else ENGINE_DEPTH

    if depth < -q_limit:
        score = evaluation(engine_board)
        if can_tt:
            tt_store(pos_hash, depth, score, TT_EXACT, None)
        return score, None

    move_list = []
    for start, ends in possible.items():
        for end in ends:
            flag = end[2:4]
            if depth > 0 or in_chk or flag in ("Xx", "Pw", "Pb", "Ep"):
                move_list.append([start, end])

    best_move = None
    if in_quiescence and not in_chk:
        stand_pat = evaluation(engine_board)
        if turn:
            if stand_pat >= beta:
                if can_tt:
                    tt_store(pos_hash, 0, stand_pat, TT_LOWER, None)
                return stand_pat, None
            alpha = max(alpha, stand_pat)
            best_score = stand_pat
        else:
            if stand_pat <= alpha:
                if can_tt:
                    tt_store(pos_hash, 0, stand_pat, TT_UPPER, None)
                return stand_pat, None
            beta = min(beta, stand_pat)
            best_score = stand_pat
        if not move_list:
            if can_tt:
                tt_store(pos_hash, 0, stand_pat, TT_EXACT, None)
            return stand_pat, None
    else:
        if not move_list:
            score = mate_or_stale(engine_board, turn, ply)
            if can_tt:
                tt_store(pos_hash, depth, score, TT_EXACT, None)
            return score, None
        best_score = -float("inf") if turn else float("inf")

    killers = KILLERS.get(ply, [])
    order_moves(move_list, engine_board, tt_move, killers)

    saw_legal = False
    for start, end in move_list:
        piece = engine_board[int(start[0])][int(start[1])]
        flag = end[2:4]
        is_cap = flag in ("Xx", "Ep") or (
                flag in ("Pw", "Pb") and engine_board[int(end[0])][int(end[1])] != "."
        )
        child_hash, undo = make_move_engine(start, end, engine_board, piece, pos_hash)
        if in_check(engine_board, turn):
            undo_move_engine(engine_board, undo)
            continue
        saw_legal = True
        moves_made.append([start, end])
        nxt = not turn
        rep_counts[child_hash] = rep_counts.get(child_hash, 0) + 1
        if rep_counts[child_hash] >= 2:
            score = DRAW_SCORE
        else:
            score, _ = engine(
                engine_board, nxt, depth - 1, alpha, beta,
                moves_made, child_hash, maximum_depth, rep_counts,
            )
        c = rep_counts[child_hash] - 1
        if c:
            rep_counts[child_hash] = c
        else:
            del rep_counts[child_hash]
        moves_made.pop()
        undo_move_engine(engine_board, undo)

        if turn:
            if score > best_score:
                best_score = score
                best_move = [start, end]
            alpha = max(alpha, best_score)
            if alpha >= beta:
                record_cutoff(start, end, is_cap, ply, depth)
                break
        else:
            if score < best_score:
                best_score = score
                best_move = [start, end]
            beta = min(beta, best_score)
            if alpha >= beta:
                record_cutoff(start, end, is_cap, ply, depth)
                break

    if not saw_legal:
        if in_quiescence and not in_chk:
            if can_tt:
                tt_store(pos_hash, 0, best_score, TT_EXACT, None)
            return best_score, None
        score = mate_or_stale(engine_board, turn, ply)
        if can_tt:
            tt_store(pos_hash, depth, score, TT_EXACT, None)
        return score, None
    if best_score <= orig_alpha:
        flag = TT_UPPER
    elif best_score >= beta:
        flag = TT_LOWER
    else:
        flag = TT_EXACT
    if can_tt:
        tt_store(pos_hash, depth, best_score, flag, best_move)
    if ply == 0 and best_move is None:
        fallback = pick_legal_move(turn, engine_board)
        if fallback is not None:
            if best_score in (float("inf"), float("-inf")):
                best_score = evaluation(engine_board)
            return best_score, fallback
    return best_score, best_move


def undo_move_engine(board, undo):
    global White_Castle, Black_Castle
    global White_Castle_Right, White_Castle_Left, Black_Castle_Right, Black_Castle_Left, EP_SQUARE
    for r, c, old in undo["squares"]:
        board[r][c] = old
    if undo["White_Castle"] is not None:
        White_Castle = undo["White_Castle"]
    if undo["Black_Castle"] is not None:
        Black_Castle = undo["Black_Castle"]
    White_Castle_Right, White_Castle_Left, Black_Castle_Right, Black_Castle_Left = undo["rights"]
    EP_SQUARE = undo["ep"]


def make_move_engine(start, end, board, piece, old_hash):
    global White_Castle, Black_Castle
    move_to_square = end
    sr, sc = int(start[0]), int(start[1])
    er, ec = int(end[0]), int(end[1])
    flag = move_to_square[2:4]
    old_rights = current_castling()
    old_ep = EP_SQUARE

    undo = {
        "squares": [],
        "White_Castle": None,
        "Black_Castle": None,
        "rights": tuple(old_rights),
        "ep": old_ep,
    }
    h = hash_toggle_ep(old_hash, old_ep)
    applied = False

    if flag == "Xx":
        captured = board[er][ec]
        undo["squares"] = [(sr, sc, piece), (er, ec, captured)]
        board[er][ec] = piece
        board[sr][sc] = "."
        h = hash_capture(h, piece, captured, sr, sc, er, ec)
        applied = True

    elif flag == "XX":
        undo["squares"] = [(sr, sc, piece), (er, ec, board[er][ec])]
        board[er][ec] = piece
        board[sr][sc] = "."
        h = hash_quiet_move(h, piece, sr, sc, er, ec)
        applied = True

    elif flag == "Wr":
        undo["White_Castle"] = White_Castle
        undo["squares"] = [
            (sr, sc, piece), (er, ec, board[er][ec]),
            (7, 5, board[7][5]), (7, 7, board[7][7]),
        ]
        White_Castle = True
        h ^= zobrist_pieces["K"][sr][sc]
        h ^= zobrist_pieces["K"][er][ec]
        h ^= zobrist_pieces["R"][7][7]
        h ^= zobrist_pieces["R"][7][5]
        h ^= zobrist_side
        board[7][5] = "R"
        board[7][7] = "."
        board[er][ec] = piece
        board[sr][sc] = "."
        applied = True

    elif flag == "Wl":
        undo["White_Castle"] = White_Castle
        undo["squares"] = [
            (sr, sc, piece), (er, ec, board[er][ec]),
            (7, 3, board[7][3]), (7, 0, board[7][0]),
        ]
        White_Castle = True
        h ^= zobrist_pieces["K"][sr][sc]
        h ^= zobrist_pieces["K"][er][ec]
        h ^= zobrist_pieces["R"][7][0]
        h ^= zobrist_pieces["R"][7][3]
        h ^= zobrist_side
        board[7][3] = "R"
        board[7][0] = "."
        board[er][ec] = piece
        board[sr][sc] = "."
        applied = True

    elif flag == "Br":
        undo["Black_Castle"] = Black_Castle
        undo["squares"] = [
            (sr, sc, piece), (er, ec, board[er][ec]),
            (0, 5, board[0][5]), (0, 7, board[0][7]),
        ]
        Black_Castle = True
        h ^= zobrist_pieces["k"][sr][sc]
        h ^= zobrist_pieces["k"][er][ec]
        h ^= zobrist_pieces["r"][0][7]
        h ^= zobrist_pieces["r"][0][5]
        h ^= zobrist_side
        board[0][5] = "r"
        board[0][7] = "."
        board[er][ec] = piece
        board[sr][sc] = "."
        applied = True

    elif flag == "Bl":
        undo["Black_Castle"] = Black_Castle
        undo["squares"] = [
            (sr, sc, piece), (er, ec, board[er][ec]),
            (0, 3, board[0][3]), (0, 0, board[0][0]),
        ]
        Black_Castle = True
        h ^= zobrist_pieces["k"][sr][sc]
        h ^= zobrist_pieces["k"][er][ec]
        h ^= zobrist_pieces["r"][0][0]
        h ^= zobrist_pieces["r"][0][3]
        h ^= zobrist_side
        board[0][3] = "r"
        board[0][0] = "."
        board[er][ec] = piece
        board[sr][sc] = "."
        applied = True

    elif flag == "Pw":
        captured = board[er][ec]
        undo["squares"] = [(sr, sc, piece), (er, ec, captured)]
        board[er][ec] = "Q"
        board[sr][sc] = "."
        if captured != ".":
            h = hash_promo(h, "P", "Q", sr, sc, er, ec, captured)
        else:
            h = hash_promo(h, "P", "Q", sr, sc, er, ec)
        applied = True

    elif flag == "Pb":
        captured = board[er][ec]
        undo["squares"] = [(sr, sc, piece), (er, ec, captured)]
        board[er][ec] = "q"
        board[sr][sc] = "."
        if captured != ".":
            h = hash_promo(h, "p", "q", sr, sc, er, ec, captured)
        else:
            h = hash_promo(h, "p", "q", sr, sc, er, ec)
        applied = True

    elif flag == "Ep":
        cap_r = er + 1 if piece == "P" else er - 1
        captured = board[cap_r][ec]
        undo["squares"] = [(sr, sc, piece), (er, ec, board[er][ec]), (cap_r, ec, captured)]
        board[er][ec] = piece
        board[sr][sc] = "."
        board[cap_r][ec] = "."
        h = hash_ep_capture(h, piece, captured, sr, sc, er, ec, cap_r, ec)
        applied = True

    if not applied:
        return old_hash, undo

    lose_castling_from_move(piece, sr, sc, er, ec)
    set_ep_after_move(piece, sr, sc, er)
    h = apply_rights_hash(h, old_rights)
    h = hash_toggle_ep(h, EP_SQUARE)
    return h, undo


def make_move(start, end, possible_moves, piece, promo=None):
    global White_Castle, Black_Castle
    valid_move = False
    move_to_square = ""
    for move in possible_moves:
        if end in move:
            valid_move = True
            move_to_square = move
            break
    if not valid_move:
        return "Move Failed"
    game_history.append([start, end])
    flag = move_to_square[2:4]
    if flag[0] == "X" and flag[1].lower() == "x":
        board[int(end[0])][int(end[1])] = piece
        board[int(start[0])][int(start[1])] = "."
        after_human_move(piece, start, end)
        return None
    if flag == "Wr":
        White_Castle = True
        board[7][5] = "R"
        board[7][7] = "."
        board[int(end[0])][int(end[1])] = piece
        board[int(start[0])][int(start[1])] = "."
        after_human_move(piece, start, end)
        return None
    if flag == "Wl":
        White_Castle = True
        board[7][3] = "R"
        board[7][0] = "."
        board[int(end[0])][int(end[1])] = piece
        board[int(start[0])][int(start[1])] = "."
        after_human_move(piece, start, end)
        return None
    if flag == "Br":
        Black_Castle = True
        board[0][5] = "r"
        board[0][7] = "."
        board[int(end[0])][int(end[1])] = piece
        board[int(start[0])][int(start[1])] = "."
        after_human_move(piece, start, end)
        return None
    if flag == "Bl":
        Black_Castle = True
        board[0][3] = "r"
        board[0][0] = "."
        board[int(end[0])][int(end[1])] = piece
        board[int(start[0])][int(start[1])] = "."
        after_human_move(piece, start, end)
        return None
    if flag == "Pw":
        chosen = promo if promo in ["Q", "R", "B", "N"] else "Q"
        board[int(end[0])][int(end[1])] = chosen
        board[int(start[0])][int(start[1])] = "."
        after_human_move(piece, start, end)
        return None
    if flag == "Pb":
        chosen = promo if promo in ["q", "r", "b", "n"] else "q"
        board[int(end[0])][int(end[1])] = chosen
        board[int(start[0])][int(start[1])] = "."
        after_human_move(piece, start, end)
        return None
    if flag == "Ep":
        er, ec = int(end[0]), int(end[1])
        cap_r = er + 1 if piece == "P" else er - 1
        board[er][ec] = piece
        board[int(start[0])][int(start[1])] = "."
        board[cap_r][ec] = "."
        after_human_move(piece, start, end)
        return None
    return "Move Failed"


def _slide(board, r, c, dirs, enemy_lower, dests):
    for dr, dc in dirs:
        nr, nc = r + dr, c + dc
        while 0 <= nr < 8 and 0 <= nc < 8:
            t = board[nr][nc]
            if t == ".":
                dests.append(str(nr) + str(nc) + "XX")
            else:
                if (enemy_lower and t.islower()) or ((not enemy_lower) and t.isupper()):
                    dests.append(str(nr) + str(nc) + "Xx")
                break
            nr += dr
            nc += dc


def generate_pseudo_moves(turn, board):
    possible_moves = {}
    enemy_lower = turn
    for r in range(8):
        for c in range(8):
            piece = board[r][c]
            if piece == ".":
                continue
            if turn and piece.islower():
                continue
            if (not turn) and piece.isupper():
                continue
            dests = []
            if piece in ("K", "k"):
                for dr, dc in KING_DIRS:
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < 8 and 0 <= nc < 8):
                        continue
                    t = board[nr][nc]
                    if t == ".":
                        dests.append(str(nr) + str(nc) + "XX")
                    elif (enemy_lower and t.islower()) or ((not enemy_lower) and t.isupper()):
                        dests.append(str(nr) + str(nc) + "Xx")
                if turn and r == 7 and c == 4:
                    if (White_Castle_Right and board[7][5] == "." and board[7][6] == "."
                            and not is_square_attacked(board, 7, 4, False)
                            and not is_square_attacked(board, 7, 5, False)
                            and not is_square_attacked(board, 7, 6, False)):
                        dests.append("76Wr")
                    if (White_Castle_Left and board[7][1] == "." and board[7][2] == "."
                            and board[7][3] == "."
                            and not is_square_attacked(board, 7, 4, False)
                            and not is_square_attacked(board, 7, 3, False)
                            and not is_square_attacked(board, 7, 2, False)):
                        dests.append("72Wl")
                if (not turn) and r == 0 and c == 4:
                    if (Black_Castle_Right and board[0][5] == "." and board[0][6] == "."
                            and not is_square_attacked(board, 0, 4, True)
                            and not is_square_attacked(board, 0, 5, True)
                            and not is_square_attacked(board, 0, 6, True)):
                        dests.append("06Br")
                    if (Black_Castle_Left and board[0][1] == "." and board[0][2] == "."
                            and board[0][3] == "."
                            and not is_square_attacked(board, 0, 4, True)
                            and not is_square_attacked(board, 0, 3, True)
                            and not is_square_attacked(board, 0, 2, True)):
                        dests.append("02Bl")
            elif piece in ("Q", "q"):
                _slide(board, r, c, QUEEN_DIRS, enemy_lower, dests)
            elif piece in ("R", "r"):
                _slide(board, r, c, ROOK_DIRS, enemy_lower, dests)
            elif piece in ("B", "b"):
                _slide(board, r, c, BISHOP_DIRS, enemy_lower, dests)
            elif piece in ("N", "n"):
                for dr, dc in KNIGHT_DIRS:
                    nr, nc = r + dr, c + dc
                    if not (0 <= nr < 8 and 0 <= nc < 8):
                        continue
                    t = board[nr][nc]
                    if t == ".":
                        dests.append(str(nr) + str(nc) + "XX")
                    elif (enemy_lower and t.islower()) or ((not enemy_lower) and t.isupper()):
                        dests.append(str(nr) + str(nc) + "Xx")
            elif piece == "P":
                if r - 1 >= 0:
                    if board[r - 1][c] == ".":
                        if r - 1 == 0:
                            dests.append(str(r - 1) + str(c) + "Pw")
                        else:
                            dests.append(str(r - 1) + str(c) + "XX")
                        if r == 6 and board[r - 2][c] == ".":
                            dests.append(str(r - 2) + str(c) + "XX")
                    for dc in (-1, 1):
                        nc = c + dc
                        if 0 <= nc < 8 and board[r - 1][nc].islower():
                            if r - 1 == 0:
                                dests.append(str(r - 1) + str(nc) + "Pw")
                            else:
                                dests.append(str(r - 1) + str(nc) + "Xx")
                if (r == 3 and EP_SQUARE is not None
                        and EP_SQUARE[0] == r - 1
                        and abs(EP_SQUARE[1] - c) == 1
                        and board[EP_SQUARE[0]][EP_SQUARE[1]] == "."):
                    dests.append(str(EP_SQUARE[0]) + str(EP_SQUARE[1]) + "Ep")
            elif piece == "p":
                if r + 1 < 8:
                    if board[r + 1][c] == ".":
                        if r + 1 == 7:
                            dests.append(str(r + 1) + str(c) + "Pb")
                        else:
                            dests.append(str(r + 1) + str(c) + "XX")
                        if r == 1 and board[r + 2][c] == ".":
                            dests.append(str(r + 2) + str(c) + "XX")
                    for dc in (-1, 1):
                        nc = c + dc
                        if 0 <= nc < 8 and board[r + 1][nc].isupper():
                            if r + 1 == 7:
                                dests.append(str(r + 1) + str(nc) + "Pb")
                            else:
                                dests.append(str(r + 1) + str(nc) + "Xx")
                if (r == 4 and EP_SQUARE is not None
                        and EP_SQUARE[0] == r + 1
                        and abs(EP_SQUARE[1] - c) == 1
                        and board[EP_SQUARE[0]][EP_SQUARE[1]] == "."):
                    dests.append(str(EP_SQUARE[0]) + str(EP_SQUARE[1]) + "Ep")
            if dests:
                possible_moves[str(r) + str(c)] = dests
    return possible_moves


def determine_possible_moves(turn, board):
    raw = generate_pseudo_moves(turn, board)
    legal = {}
    dummy_hash = 0
    for start, ends in raw.items():
        piece = board[int(start[0])][int(start[1])]
        kept = []
        for dest in ends:
            _h, undo = make_move_engine(start, dest, board, piece, dummy_hash)
            if not in_check(board, turn):
                kept.append(dest)
            undo_move_engine(board, undo)
        if kept:
            legal[start] = kept
    return legal


def game_result(board, white_turn):
    if is_insufficient_material(board):
        return "D"
    if determine_possible_moves(white_turn, board):
        return None
    if in_check(board, white_turn):
        return "B" if white_turn else "W"
    return "S"


def convert_position(position):
    columns = {
        "a": 0, "b": 1, "c": 2, "d": 3, "e": 4, "f": 5, "g": 6, "h": 7
    }
    try:
        column = columns[position[0].lower()]
        row = 8 - int(position[1])
        return row, column
    except:
        return None


def display_board():
    print("\n    a b c d e f g h")
    print("  +----------------+")
    for row in range(8):
        print(f"{8 - row} |", end=" ")
        for col in range(8):
            print(board[row][col], end=" ")
        print(f"| {8 - row}")
    print("  +----------------+")
    print("    a b c d e f g h")


def to_algebraic(square):
    s = str(square)
    r, c = int(s[0]), int(s[1])
    return "abcdefgh"[c] + str(8 - r)


def move_piece(start, end, turn):
    start_pos = convert_position(start)
    end_pos = convert_position(end)
    if start_pos is None or end_pos is None:
        print("Invalid coordinates!")
        return "Move Failed"
    possible_moves = determine_possible_moves(turn, board)
    start_row, start_col = start_pos
    end_row, end_col = end_pos
    combine_start = str(start_row) + str(start_col)
    combine_end = str(end_row) + str(end_col)
    piece = board[start_row][start_col]
    if combine_start not in possible_moves:
        return "Turn Failed"
    result = make_move(combine_start, combine_end, possible_moves[combine_start], piece)
    if result == None:
        return "Turn Made"
    else:
        return "Turn Failed"


def move_piece_game_history(start, end, turn):
    start_pos = start
    end_pos = end
    possible_moves = determine_possible_moves(turn, board)
    start_row, start_col = start_pos
    end_row, end_col = end_pos
    combine_start = str(start_row) + str(start_col)
    combine_end = str(end_row) + str(end_col)
    piece = board[int(start_row)][int(start_col)]
    if combine_start not in possible_moves:
        return "Turn Failed"
    result = make_move(combine_start, combine_end, possible_moves[combine_start], piece)
    if result == None:
        return "Turn Made"
    else:
        return "Turn Failed"


White_Turn = True


def check_king_alive(board):
    return game_result(board, White_Turn)


def castling_rights(board):
    return