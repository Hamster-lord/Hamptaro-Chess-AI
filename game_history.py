def find_game(all_games):
    if not all_games:
        print("\nNo saved games found.")
        return None

    print("\n=== GAME HISTORY ===")

    for i, game in enumerate(all_games, 1):
        try:
            white = game[1][0]
            black = game[1][1]
            game_date = game[1][2]
            moves = max(0, len(game) - 2)

            print(f"{i}) {white} vs {black} | {game_date} | {moves} moves")
        except (IndexError, TypeError):
            print(f"{i}) Unknown game")

    while True:
        choice = input("\nSelect a game (0 to cancel): ").strip()

        if choice == "0":
            return None

        if choice.isdigit():
            choice = int(choice)

            if 1 <= choice <= len(all_games):
                selected_game = all_games[choice - 1]
                print(f"\nSelected Game {choice}")
                return selected_game

        print("Invalid selection. Please enter a valid game number.")