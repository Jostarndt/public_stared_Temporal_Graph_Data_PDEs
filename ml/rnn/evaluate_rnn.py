import sys
import os
import time

import torch
from torch.utils.data import DataLoader, ConcatDataset
import numpy as np

# Set up the project root directory
ml_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
os.chdir(ml_dir)
sys.path.append(ml_dir)

from config_loader import ConfigLoader
import models
import utils

# Load config
config = ConfigLoader(os.path.abspath(os.path.join(ml_dir, "rnn", "rnn.yml"))).get_config()
device = torch.device(f"cuda:{config.device}" if torch.cuda.is_available() else "cpu")

def evaluate_model(model, validation_loader, loss_func, device, output_dir, eval_data_sources_str):
    model.eval()
    daily_loss = []
    targets_val = []
    pred_val = []

    with torch.no_grad():
        for batch_idx, data in enumerate(validation_loader):
            inputs, targets = data
            inputs = torch.permute(inputs, (2, 1, 0)).to(device)
            targets = torch.permute(targets, (2, 1, 0)).to(device)

            outputs, _ = model(inputs,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    train_mask="Yes",)


            daily_loss.append((outputs-targets).double().square().mean(axis=0).squeeze())

            targets_val.append(targets)
            pred_val.append(outputs)

    daily_loss_mean = torch.stack(daily_loss).sqrt().mean(dim=0)
    utils.daily_loss_plot(daily_loss_mean, name_string=eval_data_sources_str, output_dir=output_dir)
    utils.branch_plot(torch.stack(targets_val), torch.stack(pred_val), llv=daily_loss_mean.mean().item(), name_string=eval_data_sources_str, output_dir=output_dir)

    return daily_loss_mean, torch.stack(targets_val), torch.stack(pred_val)

loss_func = models.RMSELoss()


data_sources_list = config.datasources
eval_datasources = config.eval_datasources

for data_sources, eval_data_sources in zip(data_sources_list, eval_datasources):
    all_daily_losses = []
    for run in range(config.num_train_runs):
        eval_data_sources_str = '_'.join([ds[:4] for ds in eval_data_sources])
        data_sources_str = '_'.join([ds[:4] for ds in data_sources])
        model_dir = f"{config.model_name}_{run}_" + data_sources_str
        model_path = os.path.join(model_dir, model_dir)

        if not os.path.exists(model_path):
            print(f"Model path {model_path} does not exist. Skipping.")
            continue

        model = torch.load(model_path).to(device)
        model.device = device

        total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"Evaluating {model_dir}, number of model parameters: {total_params}")

        datasets = [utils.get_dataset(source, config, train=False) for source in eval_data_sources]
        validation_dataset = ConcatDataset([torch.utils.data.Subset(ds, range(int(0.88 * len(ds)), len(ds))) for ds in datasets])
        validation_loader = DataLoader(validation_dataset, batch_size=1, shuffle=False)

        daily_losses_model = []

        start_time = time.time()
        daily_loss, targets_val, pred_val = evaluate_model(model, validation_loader, loss_func, device, model_dir, eval_data_sources_str)
        elapsed_time = time.time() - start_time
        print(f"Elapsed time for evaluation: {elapsed_time:.2f} seconds")
        all_daily_losses.append(daily_loss.cpu().numpy())    

    np.savetxt(os.path.join("", f"{config.model_name}_{data_sources_str}-{eval_data_sources_str}_daily_losses.csv"), np.array(all_daily_losses), delimiter=",")

print("Evaluation finished")
