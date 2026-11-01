"""
LSTM / sequence model for NBA team form.

Takes a sequence of the last N games for home and away teams
(features: margin, points for/against, rest, B2B, home flag)
and outputs a win probability / expected margin contribution.

Designed to be trained walk-forward and ensembled with Elo + XGB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
except ImportError:  # pragma: no cover
    torch = None
    nn = None


SEQ_LEN = 10  # last N games per team
FEATURE_DIM = 6  # margin, pts_for, pts_against, rest_days, b2b, is_home


@dataclass
class LSTMConfig:
    seq_len: int = SEQ_LEN
    feature_dim: int = FEATURE_DIM
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2
    lr: float = 1e-3
    epochs: int = 30
    batch_size: int = 64
    device: str = "cpu"


if torch is not None:

    class TeamSequenceDataset(Dataset):
        def __init__(self, X: np.ndarray, y: np.ndarray):
            """
            X: (n_samples, 2 * seq_len, feature_dim)  # home seq + away seq
            y: (n_samples,) binary home win
            """
            self.X = torch.as_tensor(X, dtype=torch.float32)
            self.y = torch.as_tensor(y, dtype=torch.float32)

        def __len__(self):
            return len(self.y)

        def __getitem__(self, idx):
            return self.X[idx], self.y[idx]

    class MatchLSTM(nn.Module):
        """
        Dual-stream LSTM: one for home recent form, one for away.
        Concatenate final hidden states → MLP → P(home win).
        """

        def __init__(self, cfg: LSTMConfig):
            super().__init__()
            self.cfg = cfg
            self.lstm = nn.LSTM(
                input_size=cfg.feature_dim,
                hidden_size=cfg.hidden_size,
                num_layers=cfg.num_layers,
                batch_first=True,
                dropout=cfg.dropout if cfg.num_layers > 1 else 0.0,
            )
            self.head = nn.Sequential(
                nn.Linear(cfg.hidden_size * 2, 64),
                nn.ReLU(),
                nn.Dropout(cfg.dropout),
                nn.Linear(64, 1),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # x: (B, 2*seq_len, F)
            seq = self.cfg.seq_len
            home = x[:, :seq, :]
            away = x[:, seq:, :]
            _, (h_h, _) = self.lstm(home)
            _, (h_a, _) = self.lstm(away)
            # last layer hidden
            h = torch.cat([h_h[-1], h_a[-1]], dim=-1)
            logit = self.head(h).squeeze(-1)
            return logit

    def train_lstm(
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        cfg: Optional[LSTMConfig] = None,
    ) -> Tuple["MatchLSTM", dict]:
        cfg = cfg or LSTMConfig()
        device = torch.device(cfg.device)
        model = MatchLSTM(cfg).to(device)
        opt = torch.optim.Adam(model.parameters(), lr=cfg.lr)
        loss_fn = nn.BCEWithLogitsLoss()

        train_loader = DataLoader(
            TeamSequenceDataset(X_train, y_train),
            batch_size=cfg.batch_size,
            shuffle=True,
        )

        history = {"train_loss": [], "val_loss": []}
        best_state = None
        best_val = float("inf")

        for epoch in range(cfg.epochs):
            model.train()
            total = 0.0
            for xb, yb in train_loader:
                xb, yb = xb.to(device), yb.to(device)
                opt.zero_grad()
                logits = model(xb)
                loss = loss_fn(logits, yb)
                loss.backward()
                opt.step()
                total += loss.item() * len(yb)
            train_loss = total / len(y_train)
            history["train_loss"].append(train_loss)

            if X_val is not None and y_val is not None:
                model.eval()
                with torch.no_grad():
                    xv = torch.as_tensor(X_val, dtype=torch.float32).to(device)
                    yv = torch.as_tensor(y_val, dtype=torch.float32).to(device)
                    val_loss = loss_fn(model(xv), yv).item()
                history["val_loss"].append(val_loss)
                if val_loss < best_val:
                    best_val = val_loss
                    best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if best_state is not None:
            model.load_state_dict(best_state)
        return model, history

    @torch.no_grad()
    def predict_proba(model: "MatchLSTM", X: np.ndarray, device: str = "cpu") -> np.ndarray:
        model.eval()
        dev = torch.device(device)
        model = model.to(dev)
        xb = torch.as_tensor(X, dtype=torch.float32).to(dev)
        logits = model(xb)
        return torch.sigmoid(logits).cpu().numpy()

else:
    # stubs when torch is missing
    def train_lstm(*args, **kwargs):
        raise ImportError("PyTorch is required for LSTM models. pip install torch")

    def predict_proba(*args, **kwargs):
        raise ImportError("PyTorch is required for LSTM models. pip install torch")


def build_sequence_features(
    game_history: list,
    team: str,
    as_of_ts: float,
    seq_len: int = SEQ_LEN,
) -> np.ndarray:
    """
    Build a (seq_len, feature_dim) matrix of the most recent games for `team`
    strictly before as_of_ts. Pad with zeros if fewer games.

    Features: [margin, pts_for, pts_against, rest_days, b2b, is_home]
    """
    rows = []
    for g in reversed(game_history):
        if g["ts"] >= as_of_ts:
            continue
        if g["h"] != team and g["a"] != team:
            continue
        is_home = 1.0 if g["h"] == team else 0.0
        pts_for = g["gh"] if is_home else g["ga"]
        pts_against = g["ga"] if is_home else g["gh"]
        margin = pts_for - pts_against
        rest = g.get("hRest") if is_home else g.get("aRest")
        rest = float(rest) if rest is not None else 2.0
        b2b = 1.0 if (g.get("hB2B") if is_home else g.get("aB2B")) else 0.0
        rows.append([margin, pts_for, pts_against, rest, b2b, is_home])
        if len(rows) >= seq_len:
            break

    rows = list(reversed(rows))  # chronological
    while len(rows) < seq_len:
        rows.insert(0, [0.0] * FEATURE_DIM)
    return np.asarray(rows[-seq_len:], dtype=np.float32)
