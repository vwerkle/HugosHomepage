import json
import statsapi
import requests
from flask import Flask, render_template, request, redirect,url_for, Blueprint

moonshot_bp = Blueprint('moonshot',__name__)
API_ENDPOINT="https://api.mlb.com/stats/homeruns"

def get_players(filepath):
    with open(filepath,'r') as file:
        data= json.load(file)
        return data

def get_home_runs(player_ids):
    home_run_counts={}
    print(player_ids)
    for player_name, player_id in player_ids.items():
        player_stats= statsapi.player_stat_data(player_id,group="hitting",type="season")
        #print(player_stats['stats']['homeRuns'])
        #print(player_stats)

        #print(player_stats['stats'][0]['stats']['homeRuns'])
        home_runs = player_stats['stats'][0]['stats']['homeRuns']
        home_run_counts[player_name]=home_runs
    return home_run_counts

def process_groups(filepath):
    data =get_players(filepath)
    group_stats={}
    for group,players in data.items():
        home_run_counts=get_home_runs(players)
        sorted_players = sorted(home_run_counts.items(), key=lambda x:x[1], reverse=True)
        min_home_run_player = sorted_players[-1]
        total_home_runs=sum(home_run_counts.values())-min(home_run_counts.values())
        group_stats[group]={
            'players':sorted_players,
            'total_home_runs':total_home_runs,
            'min_home_run_player':min_home_run_player[0]
        }
    sorted_groups = sorted(group_stats.items(), key=lambda x:x[1]['total_home_runs'],reverse=True)
    return sorted_groups

@moonshot_bp.route("/moonshot")
def moonshot():
    sorted_groups=process_groups("moonshot.json")
    print(sorted_groups)
    return render_template('moonshot.html', groups=sorted_groups)