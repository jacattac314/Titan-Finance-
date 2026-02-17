import torch
import torch.nn as nn

class AttentionBlock(nn.Module):
    def __init__(self, hidden_size):
        super(AttentionBlock, self).__init__()
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1)
        )

    def forward(self, x):
        # x: [batch, seq_len, hidden_size]
        weights = self.attention(x) # [batch, seq_len, 1]
        weights = torch.softmax(weights, dim=1)
        return torch.sum(x * weights, dim=1) # [batch, hidden_size]

class LSTMModel(nn.Module):
    def __init__(self, input_size=14, hidden_size=64, num_layers=2, dropout=0.2):
        super(LSTMModel, self).__init__()
        
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout
        )
        
        self.attention = AttentionBlock(hidden_size)
        
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        # x: [batch, seq_len, input_size]
        out, _ = self.lstm(x) # out: [batch, seq_len, hidden_size]
        context = self.attention(out) # context: [batch, hidden_size]
        prediction = self.fc(context) # [batch, 1]
        return prediction
