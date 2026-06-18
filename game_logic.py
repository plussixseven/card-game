import random
from typing import Optional

SUITS = ['+', '☽', '♚', '☀']
RANKS = ['В', 'Д', 'К', 'Т', '6', '7', '8']
RANK_ORDER = {r: i for i, r in enumerate(RANKS)}  # В=0 ... 8=6
TRUMP_SUIT = '♚'
CROSS_SUIT = '+'


def make_deck():
    deck = [{'suit': s, 'rank': r} for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck


def card_str(card):
    return f"{card['rank']}{card['suit']}"


def card_beats(attacker, defender):
    """
    Может ли defender покрыть attacker?
    Возвращает True/False.
    Особые случаи обрабатываются в game loop отдельно.
    """
    ar, as_ = attacker['rank'], attacker['suit']
    dr, ds = defender['rank'], defender['suit']

    # 6-ки не крывают — они только переворачивают
    if dr == '6':
        return False

    # 8 — джокер по масти: закрывает любую карту той же масти
    if dr == '8':
        return ds == as_

    # Д+ — бьёт всё
    if dr == 'Д' and ds == '+':
        return True

    # Крестовые (+) крываются только крестом
    if as_ == CROSS_SUIT:
        if ds != CROSS_SUIT:
            return False
        # В кресте 7 выше туза (8 уже обработан выше)
        if ar == '7':
            return False  # 7 бьёт всё кроме Д+ и 8+, но 7 не бьёт другую 7
        if dr == '7':
            return True
        return RANK_ORDER[dr] > RANK_ORDER[ar]

    # Козырь бьёт любую некрестовую некозырную
    if ds == TRUMP_SUIT and as_ != CROSS_SUIT and as_ != TRUMP_SUIT:
        return True

    # Козырь бьёт козырь
    if ds == TRUMP_SUIT and as_ == TRUMP_SUIT:
        if ar == '7':
            return False
        if dr == '7':
            return True
        return RANK_ORDER[dr] > RANK_ORDER[ar]

    # Одна масть
    if ds == as_:
        if ar == '7':
            return False
        if dr == '7':
            return True
        return RANK_ORDER[dr] > RANK_ORDER[ar]

    return False


class CardGame:
    def __init__(self, player_ids: list):
        self.players = player_ids[:]          # list of user_id strings
        self.hands = {}
        self.direction = -1                   # -1 = против часовой (left), +1 = по часовой
        self.table = []                       # карты на столе [{'card':..,'owner':..}]
        self.discard = []
        self.current_idx = 0                  # индекс того, кто ХОДИТ сейчас
        self.state = 'playing'               # playing / finished
        self.loser = None
        self.first_card_info = None           # карта для определения первого хода
        self.phase = 'deal'                   # deal / play

        deck = make_deck()
        per_player = len(deck) // len(player_ids)
        for i, pid in enumerate(player_ids):
            self.hands[pid] = deck[i*per_player:(i+1)*per_player]

        # Определяем карту первого хода
        self._find_first_player()

    def _find_first_player(self):
        # Ищем карту: например 6♚ или В+ — по правилам у кого есть определённая карта
        # По условию: система показывает карту, наличие которой даёт право первого хода
        # Выберем случайную карту из колоды и найдём кто ею владеет
        target = {'suit': TRUMP_SUIT, 'rank': '6'}  # 6♚ — стартовая карта
        for i, pid in enumerate(self.players):
            for c in self.hands[pid]:
                if c['rank'] == target['rank'] and c['suit'] == target['suit']:
                    self.current_idx = i
                    self.first_card_info = target
                    return
        # Если никто не имеет — берём В+
        target2 = {'suit': '+', 'rank': 'В'}
        for i, pid in enumerate(self.players):
            for c in self.hands[pid]:
                if c['rank'] == target2['rank'] and c['suit'] == target2['suit']:
                    self.current_idx = i
                    self.first_card_info = target2
                    return
        # Fallback: первый игрок
        self.first_card_info = {'suit': '?', 'rank': '?'}
        self.current_idx = 0

    def current_player(self):
        return self.players[self.current_idx]

    def next_idx(self, idx=None, steps=1):
        if idx is None:
            idx = self.current_idx
        n = len(self.players)
        return (idx + self.direction * steps) % n

    def _remove_finished_players(self):
        """Убираем игроков без карт (они победили)."""
        finished = [p for p in self.players if len(self.hands[p]) == 0]
        for p in finished:
            self.players.remove(p)
            del self.hands[p]
        if len(self.players) == 1:
            self.state = 'finished'
            self.loser = self.players[0]

    def play_card(self, player_id, card_idx):
        """
        Игрок player_id кидает карту с индексом card_idx из своей руки.
        Возвращает dict с результатом действия.
        """
        if self.state == 'finished':
            return {'ok': False, 'msg': 'Игра окончена'}
        if player_id != self.current_player():
            return {'ok': False, 'msg': 'Сейчас не ваш ход'}

        hand = self.hands[player_id]
        if card_idx < 0 or card_idx >= len(hand):
            return {'ok': False, 'msg': 'Нет такой карты'}

        card = hand[card_idx]
        result = {'ok': True, 'events': []}

        # Если стол пуст — просто кладём карту (первый ход в раунде)
        if not self.table:
            hand.pop(card_idx)
            self.table.append({'card': card, 'owner': player_id})
            result['events'].append({'type': 'play', 'player': player_id, 'card': card_str(card)})
            self.current_idx = self.next_idx()
            self._check_table_full(result)
            self._remove_finished_players()
            return result

        top = self.table[-1]['card']

        # Случай: 6-ка — переворот
        if card['rank'] == '6':
            # 6 не может перевернуть 7 или карты масти +
            if top['rank'] == '7' or top['suit'] == CROSS_SUIT:
                return {'ok': False, 'msg': '6 не может перевернуть 7 или карту масти +'}
            hand.pop(card_idx)
            # 6♚ — особое поведение
            if card['suit'] == TRUMP_SUIT:
                self.direction *= -1
                self.table.append({'card': card, 'owner': player_id})
                # Всё что на столе улетает в биту
                self.discard.extend([e['card'] for e in self.table])
                self.table = []
                result['events'].append({'type': '6trump', 'player': player_id, 'card': card_str(card), 'msg': 'Козырная 6! Разворот и всё в биту'})
                self.current_idx = self.next_idx()
            else:
                self.direction *= -1
                self.table.append({'card': card, 'owner': player_id})
                result['events'].append({'type': '6flip', 'player': player_id, 'card': card_str(card), 'msg': 'Разворот направления!'})
                self.current_idx = self.next_idx()
                self._check_table_full(result)
            self._remove_finished_players()
            return result

        # Обычное покрытие
        if card_beats(top, card):
            hand.pop(card_idx)
            self.table.append({'card': card, 'owner': player_id})
            result['events'].append({'type': 'beat', 'player': player_id, 'card': card_str(card)})

            # 7 когда крайней — разворот
            if card['rank'] == '7':
                self.direction *= -1
                result['events'].append({'type': 'flip', 'msg': '7 разворачивает ход!'})

            # Д+ — бьёт всё, ходит тот кто кинул
            if card['rank'] == 'Д' and card['suit'] == '+':
                self.discard.extend([e['card'] for e in self.table])
                self.table = []
                result['events'].append({'type': 'Dplus', 'msg': 'Д+ всё бьёт! Ход снова у вас'})
                # current_idx остаётся тем же (игрок ходит снова)
                self._remove_finished_players()
                return result

            # 8 — джокер: переворачивает направление того кто покрылся
            if card['rank'] == '8':
                self.direction *= -1
                result['events'].append({'type': '8joker', 'msg': '8 — джокер, разворот!'})

            self.current_idx = self.next_idx()
            self._check_table_full(result)
            self._remove_finished_players()
            return result

        # Не может покрыть — поднимает нижнюю карту
        bottom = self.table[0]['card']
        hand.pop(card_idx)
        hand.append(bottom)
        self.table[0] = self.table[1] if len(self.table) > 1 else {'card': card, 'owner': player_id}
        # Перекладываем: нижняя уходит к игроку, текущая карта становится нижней
        # Правильно: игрок ПОДНИМАЕТ нижнюю (берёт в руку), его карта ложится снизу
        self.table.insert(0, {'card': card, 'owner': player_id})
        self.table.pop(1)  # убираем ту что подняли (она уже в руке)
        result['events'].append({'type': 'take', 'player': player_id, 'card': card_str(bottom), 'msg': 'Не смог покрыть — берёт нижнюю карту'})
        self.current_idx = self.next_idx()
        self._remove_finished_players()
        return result

    def _check_table_full(self, result):
        """Если на столе столько карт сколько игроков — убираем в биту."""
        if len(self.table) >= len(self.players):
            last_owner = self.table[-1]['owner']
            self.discard.extend([e['card'] for e in self.table])
            self.table = []
            result['events'].append({'type': 'clear', 'msg': 'Стол в биту!'})
            # Ходит тот кто крылся последним
            self.current_idx = self.players.index(last_owner)
            self.current_idx = self.next_idx(self.current_idx, 0)

    def get_state(self, for_player=None):
        state = {
            'players': self.players,
            'direction': self.direction,
            'table': [{'card': card_str(e['card']), 'owner': e['owner']} for e in self.table],
            'hand_sizes': {p: len(self.hands[p]) for p in self.players},
            'current': self.current_player() if self.players else None,
            'state': self.state,
            'loser': self.loser,
            'first_card': card_str(self.first_card_info) if self.first_card_info else None,
        }
        if for_player and for_player in self.hands:
            state['hand'] = [card_str(c) for c in self.hands[for_player]]
            state['hand_raw'] = self.hands[for_player]
        return state
