# demo_bot.py — for Replit testing

from utils.referral_link import referral_link

def show_referral(user_id):
    link = referral_link(str(user_id))
    print(f"Referral link for user {user_id}: {link}")

def show_leaderboard():
    leaderboard = [
        ("user1", 5, 120),
        ("user2", 3, 80),
        ("user3", 2, 50)
    ]
    medals = ["🥇", "🥈", "🥉"]
    for i, (username, wins, earnings) in enumerate(leaderboard):
        medal = medals[i] if i < 3 else "🔹"
        print(f"{medal} @{username} – {wins} wins, {earnings} birr")

def simulate_cartela():
    print("Cartela preview: [12, 34, 56, 78, 90]")

# Run demo
show_referral(364344971)
show_leaderboard()
simulate_cartela()
