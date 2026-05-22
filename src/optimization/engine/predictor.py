from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from src.optimization.config import get_optimization_config
from src.optimization.models.lstm_model import MultiVarLSTM


class LSTMPredictor:
    def __init__(self, input_size: int):
        cfg = get_optimization_config()
        self.cfg = cfg
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = MultiVarLSTM(
            input_size=input_size,
            hidden_size=cfg.lstm_hidden_size,
            num_layers=cfg.lstm_num_layers,
            dropout=cfg.lstm_dropout,
        ).to(self.device)
        self.criterion = nn.SmoothL1Loss()
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=cfg.lstm_lr)

    def create_windows(self, features, target, window_size: int):
        x_values, y_values = [], []
        for i in range(len(features) - window_size):
            x_values.append(features[i: i + window_size])
            y_values.append(target[i + window_size])
        return (
            torch.tensor(np.array(x_values), dtype=torch.float32),
            torch.tensor(np.array(y_values), dtype=torch.float32),
        )

    def train(self, train_loader, val_loader, part_name: str):
        save_dir = Path(self.cfg.model_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"{part_name}_best.pth"
        for _ in range(self.cfg.lstm_epochs):
            self.model.train()
            for batch_x, batch_y in train_loader:
                batch_x, batch_y = batch_x.to(self.device), batch_y.to(self.device)
                self.optimizer.zero_grad()
                loss = self.criterion(self.model(batch_x), batch_y)
                loss.backward()
                self.optimizer.step()
        torch.save(self.model.state_dict(), save_path)
        return str(save_path)

    def forecast_future(self, current_window, scaler_target, steps: int = 4) -> list[int]:
        self.model.eval()
        predictions = []
        window = current_window.copy()
        for _ in range(steps):
            input_tensor = torch.tensor([window], dtype=torch.float32).to(self.device)
            with torch.no_grad():
                pred_scaled = self.model(input_tensor).item()
            pred_raw = scaler_target.inverse_transform([[pred_scaled]])[0][0]
            pred_int = int(max(0, np.round(pred_raw)))
            predictions.append(pred_int)
            new_row = window[-1].copy()
            new_row[0] = pred_scaled
            window = np.append(window[1:], [new_row], axis=0)
        return predictions
