import os

from apscheduler.schedulers.background import BackgroundScheduler
import os.path
import glob
import json
import datetime
import uuid
from datetime import datetime as dt
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask import send_from_directory
from helpers import login_required, allowed_file, crop_max_square
from PIL import Image, ImageDraw, ImageFilter

# 画像のアップロード先のディレクトリ
UPLOAD_FOLDER = './static'



app = Flask(__name__)

app.config["TEMPLATES_AUTO_RELOAD"] = True

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["ENV"] = "development"
# 画像のアップロード
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
Session(app)


db = SQL("sqlite:///doitter.db")

scheduler = BackgroundScheduler()
@scheduler.scheduled_job('interval', seconds=60)
def job_0():
    #今日の日付を取得
    today=datetime.datetime.now()+datetime.timedelta(hours=9)
    today=today.strftime('%Y/%m/%d')
    #期限切れのタスクを取得
    tasks=db.execute("SELECT * FROM tasks WHERE limit_at != '' AND limit_at < ? AND is_completed = ?",today,0)
    if len(tasks) != 0:
        for task in tasks:
            db.execute("UPDATE tasks SET is_completed = 2 WHERE id = ?",task['id'])
            content="「"+task['content']+"」"+"の期限が過ぎました..."
            created_time=datetime.datetime.strptime(task['limit_at'], '%Y/%m/%d')
            #created_time=created_time+datetime.timedelta(days=1)
            today=datetime.datetime.now()+datetime.timedelta(hours=9)
            created_time=today.strftime('%Y/%m/%d %H:%M:%S')
            db.execute("INSERT INTO tweets (content,created_at,is_completed,user_id) VALUES(?,?,?,?)",content,created_time,2,task['user_id'])


    print('60秒毎に実行')
scheduler.start()



#--タイムライン画面のバックエンド--
@app.route("/")
@login_required
def index():
    #フォローしてる人一覧から、ツイート情報を取得
    login_user=session["user_id"]
    tweets = db.execute("SELECT * FROM tweets WHERE user_id IN (SELECT following_id FROM relations WHERE followed_id = ?) or user_id = ? AND is_deleted = 0 ORDER BY created_at DESC",login_user,login_user)

    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", login_user)[0]

    for tweet in tweets:

        #ツイートIDからいいね数を取得
        good_count=db.execute("SELECT count(id) FROM favorites WHERE tweet_id = ?",tweet['id'])[0]['count(id)']
        tweet['good_count'] = good_count
        #ツイートIDからコメント数取得
        comment_count=db.execute("SELECT count(id) FROM comments WHERE tweet_id = ? AND is_deleted = 0",tweet['id'])[0]['count(id)']
        tweet['comment_count'] = comment_count
        #アカウント名を取得
        user=db.execute("SELECT account_name,name FROM users WHERE id = ?",tweet['user_id'])
        account_name=user[0]['account_name']
        tweet['account_name'] = account_name
        #ユーザーネームを取得
        name=user[0]['name']
        tweet['name']=name
        #自分がいいねしてるかを取得(してなかったら0,してたら1)
        good=db.execute("SELECT count(id) FROM favorites WHERE tweet_id = ? AND user_id = ?",tweet['id'],login_user)[0]['count(id)']
        tweet['good']=good

        # アイコンの取得
        tweet['user_icon'] = db.execute("SELECT icon FROM users WHERE id = ?", tweet['user_id'])[0]['icon']

    return render_template("home/timeline.html",tweets=tweets,login_user=login_user, layout_icon=layout_icon)


@app.route("/delete/tweet/<int:tweet_id>")
def delete_tweet(tweet_id):

    db.execute("UPDATE tweets SET is_deleted = 1 WHERE id = ?",tweet_id)

    return redirect(url_for('index'))


@app.route("/good",methods=["POST"])
@login_required
def good():
    login_user=session["user_id"]
    print(request.json)
    tweet_id = request.json["tweet_id"]
    tweet = db.execute("SELECT * FROM tweets WHERE id = ?",tweet_id)[0]

    #自分がいいねしてるかを取得
    good_self=db.execute("SELECT count(id) FROM favorites WHERE tweet_id = ? AND user_id = ?",tweet_id,login_user)[0]['count(id)']
    #投稿のいいね数を取得
    good=db.execute("SELECT count(id) FROM favorites WHERE tweet_id = ?",tweet['id'])[0]['count(id)']
    tweet['good']=good
    #してないとき0,してるとき1
    if good_self == 1:
        db.execute("DELETE FROM favorites WHERE tweet_id = ? AND user_id = ?",tweet_id,login_user)
        tweet['good'] = tweet['good'] - 1
    elif good_self == 0:
        db.execute("INSERT INTO favorites (tweet_id,user_id) VALUES (?,?)",tweet_id,login_user)
        tweet['good'] = tweet['good'] + 1

    return_json = {
       "tweet_good":tweet['good']
    }
    return jsonify(values=json.dumps(return_json))


@app.route("/post/delete",methods=["POST"])
def post_delete():

    tweet_id = request.json["tweet_id"]
    db.execute("UPDATE tweets SET is_deleted = 1 WHERE id = ?",tweet_id)
    return_json = {"true":"true"}

    return jsonify(values=json.dumps(return_json))


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        # usernameを打つところが空白じゃないか
        if not request.form.get("username"):
            flash("Usernameを入力してください。", category="error")
            return redirect("/login")

        # passwordを打つところが空白じゃ無いかどうか
        elif not request.form.get("password"):
            flash("Passwordを入力してください。", category="error")
            return redirect("/login")

        rows = db.execute("SELECT * FROM users WHERE name = ?", request.form.get("username"))

        # username が存在するか password が正しいか確かめる
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
           flash("Username、またはPasswordが正しくありません。", category="error")
           return redirect("/login")

        session["user_id"] = rows[0]["id"]

        return redirect("/")
    else:
        return render_template("auth/login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if (request.method == "POST"):
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        account_name = request.form.get("account_name")

        if not username:
            flash("Usernameを入力してください。", category="error")
            return redirect("/register")
        elif not password:
            flash("Passwordを入力してください。", category="error")
            return redirect("/register")
        elif not confirmation:
            flash("Confirmation-passwordを入力してください。", category="error")
            return redirect("/register")
        elif not account_name:
            flash("Account-nameを入力してください。", category="error")
            return redirect("/register")

        if password != confirmation:
            flash("Passwordが一致しません。", category="error")
            return redirect("/register")

        hash = generate_password_hash(password)

        try:
            db.execute("INSERT INTO users (name, hash, account_name) VALUES (?, ?, ?)", username, hash, account_name)
            return redirect('/')
        except:
            flash("Username has already been registered.", category="error")
            return redirect("/register")

    else:
        return render_template("auth/register.html")


#--todo画面のバックエンド↓

#編集
@app.route("/edit/todo/<int:id>",methods=["GET","POST"])
@login_required
def edit_todo(id):
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]
    if request.method == "POST":
        #タスク内容取得
        content=request.form.get("task")
        #タスク期限取得
        limit=request.form.get("limit")
        if limit != '':
            limit_date=dt.strptime(limit,'%Y-%m-%d').strftime('%Y/%m/%d')
        else:
            limit_date=''
        #現在の日時を取得してDBのフォーマットに変換
        now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute("UPDATE tasks SET content = ?,limit_at = ?,updated_at = ? WHERE id = ?",content,limit_date,now,id)
        tasks = db.execute("SELECT * FROM tasks WHERE user_id = ? and is_completed = ? and is_deleted = ? ORDER BY (limit_at IS ''),limit_at",session["user_id"],0,0)
        edit_task_id = id
        return redirect(url_for('todo',id=session["user_id"]))
    else:
        #ログインしてるユーザーの未完了タスクを取得
        tasks = db.execute("SELECT * FROM tasks WHERE user_id = ? and is_completed != ? and is_deleted = ? ORDER BY (limit_at IS ''),limit_at",session["user_id"],1,0)
        #編集するタスクのID
        edit_task_id = id
        #プロフィール表示するのユーザー情報の取得
        profile = db.execute("SELECT id, name AS user_name, account_name, icon FROM users WHERE id = ?", session['user_id'])[0]

        #フォロー、フォロワー数を追加
        profile["following_count"] = db.execute("SELECT count(id) FROM relations WHERE followed_id = ?", session['user_id'])[0]['count(id)']
        profile["followers_count"] = db.execute("SELECT count(id) FROM relations WHERE following_id = ?", session['user_id'])[0]['count(id)']

        # todo、doneの数を取得する
        profile["todo_count"] = db.execute("SELECT count(id) FROM tasks WHERE is_completed != ? and is_deleted = ? and user_id = ?", 1, 0, profile_id)[0]['count(id)']
        profile["done_count"] = db.execute("SELECT count(id) FROM tasks WHERE is_completed = ? and user_id = ?", 1, session['user_id'])[0]['count(id)']
        #今日の日付を取得
        today=datetime.datetime.now()+datetime.timedelta(hours=9)
        today=today.strftime('%Y/%m/%d')
        #明日の日付を取得
        tommorow=datetime.datetime.now()+datetime.timedelta(hours=9)+datetime.timedelta(days=1)
        tommorow=tommorow.strftime("%Y/%m/%d")
        return render_template("home/profile/edit_todo.html",tasks=tasks,edit_task_id=edit_task_id, profile=profile,layout_icon=layout_icon,tommorow=tommorow,today=today)


#削除
@app.route("/delete/todo/<int:id>")
@login_required
def delete_todo(id):
    #削除フラグを立てる
    db.execute("UPDATE tasks SET is_deleted = ? WHERE id = ?",1,id)
    #タスクが未完了が完了済みかを取得
    task_status = db.execute("SELECT is_completed FROM tasks WHERE id = ?",id)[0]['is_completed']
    #タスクの完了状況によって、リダイレクト先を変える
    if task_status != 1:
        return redirect(url_for('todo',id=session["user_id"]))
    else:
        return redirect(url_for('done',id=session["user_id"]))




@app.route("/todo/<int:id>")
@login_required
def todo(id):
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]
    #ログインしているユーザー
    login_user = session["user_id"]
    #プロフィールのユーザー
    profile_id = id

    #プロフィール表示するのユーザー情報の取得
    profile = db.execute("SELECT id, name AS user_name, account_name, icon FROM users WHERE id = ?", profile_id)[0]

    #フォロー、フォロワー数を追加
    profile["following_count"] = db.execute("SELECT count(id) FROM relations WHERE followed_id = ?", profile_id)[0]['count(id)']
    profile["followers_count"] = db.execute("SELECT count(id) FROM relations WHERE following_id = ?", profile_id)[0]['count(id)']

    # todo、doneの数を取得する
    profile["todo_count"] = db.execute("SELECT count(id) FROM tasks WHERE is_completed != ? and is_deleted = ? and user_id = ?", 1, 0, profile_id)[0]['count(id)']
    profile["done_count"] = db.execute("SELECT count(id) FROM tasks WHERE is_completed = ? and user_id = ?", 1, profile_id)[0]['count(id)']

    #プロフィールのユーザーの未完了タスクを取得
    tasks = db.execute("SELECT * FROM tasks WHERE user_id = ? and is_completed != ? and is_deleted = ? ORDER BY (limit_at IS ''),limit_at",profile_id,1,0)
    #今日の日付を取得
    today=datetime.datetime.now()+datetime.timedelta(hours=9)
    today=today.strftime('%Y/%m/%d')
    #明日の日付を取得
    tommorow=datetime.datetime.now()+datetime.timedelta(hours=9)+datetime.timedelta(days=1)
    tommorow=tommorow.strftime("%Y/%m/%d")
    return render_template("home/profile/todo.html",tasks=tasks,login_user=login_user,profile_id=profile_id, profile=profile,tommorow=tommorow,today=today, layout_icon=layout_icon)


@app.route("/done/<int:id>")
@login_required
def done(id):
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]
    #ログインしているユーザー
    login_user = session["user_id"]
    #プロフィールのユーザー
    profile_id = id

    #プロフィール表示するのユーザー情報の取得
    profile = db.execute("SELECT id, name AS user_name, account_name, icon FROM users WHERE id = ?", profile_id)[0]

    #フォロー、フォロワー数を追加
    profile["following_count"] = db.execute("SELECT count(id) FROM relations WHERE followed_id = ?", profile_id)[0]['count(id)']
    profile["followers_count"] = db.execute("SELECT count(id) FROM relations WHERE following_id = ?", profile_id)[0]['count(id)']

    # todo、doneの数を取得する
    profile["todo_count"] = db.execute("SELECT count(id) FROM tasks WHERE is_completed != ? and is_deleted = ? and user_id = ?", 1, 0, profile_id)[0]['count(id)']
    profile["done_count"] = db.execute("SELECT count(id) FROM tasks WHERE is_completed = ? and user_id = ?", 1, profile_id)[0]['count(id)']

    #プロフィールのユーザーの完了済みのタスクを取得
    completes = db.execute("SELECT * FROM tasks WHERE user_id = ? and is_completed = ? and is_deleted = ? ORDER BY updated_at DESC",profile_id,1,0)
    return render_template("home/profile/done.html",login_user=login_user,profile_id=profile_id,completes=completes, profile=profile, layout_icon=layout_icon)

@app.route("/add/todo",methods=['POST'])
def add():
    id=session["user_id"]
    task=request.form.get("task")
    limit=request.form.get("limit")
    if limit != '':
        limit_date=dt.strptime(limit,'%Y-%m-%d').strftime('%Y/%m/%d')
    else:
        limit_date=''
    #投稿の作成時間を取得
    created_time=datetime.datetime.now()+datetime.timedelta(hours=9)
    created_time=created_time.strftime("%Y/%m/%d %H:%M:%S")
    content="「"+task+"」を作成しました!"
    db.execute("INSERT INTO tweets (content,created_at,is_completed,user_id) VALUES(?,?,?,?)",content,created_time,0,session["user_id"])
    db.execute("INSERT INTO tasks (content,limit_at,user_id) VALUES(?,?,?)",task,limit_date,session["user_id"])
    return redirect(url_for('todo',id=session["user_id"]))




@app.route("/check/<int:id>")
def check(id):

    #現在の時刻を取得し、dbで保存されている日時の形式に変換
    now=datetime.datetime.now()+datetime.timedelta(hours=9)
    now=now.strftime("%Y-%m-%d %H:%M:%S")
    completed_date = dt.strptime(now,'%Y-%m-%d %H:%M:%S').strftime('%Y/%m/%d')
    db.execute("UPDATE tasks SET is_completed = ?,completed_at = ?,updated_at = ? WHERE id = ?",1,completed_date,now,id)
    #タスク内容を取得
    task=db.execute("SELECT * FROM tasks WHERE id = ?",id)[0]['content']
    content="「"+task+"」を完了しました!"
    #投稿の作成時間を取得
    created_time=datetime.datetime.now()+datetime.timedelta(hours=9)
    created_time=created_time.strftime("%Y/%m/%d %H:%M:%S")
    db.execute("INSERT INTO tweets (content,created_at,is_completed,user_id) VALUES(?,?,?,?)",content,created_time,1,session["user_id"])
    return redirect(url_for('todo',id=session["user_id"]))


#--todo画面のバックエンド↑

# フォローフォロワー検索、フォロー、フォローフォロワー一覧機能
@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]

    if request.method == "POST":
        username = request.form.get("username")
        # 検索内容がデータベースに存在していた場合
        # 要注意のポイント、エラーの原因である可能性あり
        try:
            # 検索したユーザーの情報を取得
            searched_user = db.execute("SELECT * FROM users WHERE name = ?", username)[0]

            # todo、doneの数を取得する
            searched_user["todo_count"] = db.execute(
                """
                SELECT count(t.id) FROM tasks AS t
                JOIN users AS u ON t.user_id = u.id
                WHERE is_completed != ?
                and is_deleted = ?
                and u.name = ?
                """
                , 1, 0, username)[0]['count(t.id)']
            searched_user["done_count"] = db.execute(
                """
                SELECT count(t.id) FROM tasks AS t
                JOIN users AS u ON t.user_id = u.id
                WHERE is_completed = ?
                and u.name = ?
                """
                , 1, username)[0]['count(t.id)']

            # ログインしているユーザーが既にフォローしているかを確認する
            searched_user["is_login_user_following"] = db.execute(
                """
                SELECT COUNT(id) FROM relations
                WHERE followed_id = ?
                AND following_id = ?
                """
                , session["user_id"], searched_user["id"])[0]['COUNT(id)']

            return render_template("home/search.html", searched_user=searched_user,layout_icon=layout_icon)

        except IndexError:
            error = 'No results for \"' + username + '\"'
            return render_template("home/search.html", error=error,layout_icon=layout_icon)

    else:
        return render_template("home/search.html",layout_icon=layout_icon)

@app.route("/<int:user_id>/followingList", methods=["GET"])
@login_required
def followingList(user_id):
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]
    following_users = db.execute(
        """
        SELECT following_id AS id, name, account_name FROM relations AS rel
        JOIN users AS u ON rel.following_id = u.id
        WHERE rel.followed_id = ?
        """
        , user_id)

    for following_user in following_users:
        # todo、doneの数を取得する
        following_user["todo_count"] = db.execute(
            """
            SELECT count(id) FROM tasks
            WHERE is_completed != ?
            and is_deleted = ?
            and user_id = ?
            """
            , 1, 0, following_user['id'])[0]['count(id)']
        following_user["done_count"] = db.execute(
            """
            SELECT count(id) FROM tasks
            WHERE is_completed = ?
            and user_id = ?
            """
            , 1, following_user['id'])[0]['count(id)']

        # ログインしているユーザーが既にフォローしているユーザーかを取得する
        following_user["is_login_user_following"] = db.execute(
            """
            SELECT COUNT(id) FROM relations
            WHERE followed_id = ?
            AND following_id = ?
            """
            , session["user_id"], following_user["id"])[0]['COUNT(id)']

        # アイコンの取得
        following_user['user_icon'] = db.execute("SELECT icon FROM users WHERE id = ?", following_user["id"])[0]['icon']

    return render_template("home/profile/following.html", user_id=user_id, following_users=following_users,layout_icon=layout_icon)



@app.route("/<int:user_id>/followersList", methods=["GET"])
@login_required
def followersList(user_id):
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]
    followers = db.execute(
        """
        SELECT followed_id AS id, name, account_name FROM relations AS rel
        JOIN users AS u ON rel.followed_id = u.id
        WHERE rel.following_id = ?
        """
        , user_id)

    for follower in followers:
        # todo、doneの数を取得する
        follower["todo_count"] = db.execute(
            """
            SELECT count(id) FROM tasks
            WHERE is_completed != ?
            and is_deleted = ?
            and user_id = ?
            """
            , 1, 0, follower['id'])[0]['count(id)']
        follower["done_count"] = db.execute(
            """
            SELECT count(id) FROM tasks
            WHERE is_completed = ?
            and user_id = ?
            """
            , 1, follower['id'])[0]['count(id)']

        # ログインしているユーザーが既にフォローしているユーザーかを取得する
        follower["is_login_user_following"] = db.execute(
            """
            SELECT COUNT(id) FROM relations
            WHERE followed_id = ?
            AND following_id = ?
            """
            , session["user_id"], follower["id"])[0]['COUNT(id)']

        # アイコンの取得
        follower['user_icon'] = db.execute("SELECT icon FROM users WHERE id = ?", follower["id"])[0]['icon']

    return render_template("home/profile/followers.html", user_id=user_id, followers=followers,layout_icon=layout_icon)



@app.route('/follow_unfollow', methods=["POST"])
@login_required
def follow_unfollow():
    # フォローまたは、フォロー解除するユーザーのIDを取得
    user_id = request.json["user_id"]
    # ログインしているユーザーが既にフォローしているユーザーかどうかを取得
    login_user_is_following = db.execute(
        """
        SELECT COUNT(id) FROM relations
        WHERE followed_id = ?
        AND following_id = ?
        """
        , session["user_id"], user_id)[0]['COUNT(id)']

    # フォローしている場合(1)、フォローしていない場合(0)
    if login_user_is_following:
        db.execute(
            """
            DELETE FROM relations
            WHERE followed_id = ?
            AND following_id = ?
            """
            , session["user_id"], user_id)
        # フォロー解除した
        login_user_is_followed = 0
    else:
        db.execute(
            """
            INSERT INTO relations (followed_id, following_id)
            VALUES(?, ?)
            """
            , session["user_id"], user_id)
        # フォローした
        login_user_is_followed = 1

    return_json = {
        "is_followed": login_user_is_followed
    }

    return jsonify(values=json.dumps(return_json))



# comment画面
@app.route("/comment/<int:tweet_id>")
@login_required
def comment(tweet_id):
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]
    ## comment画面でタスク作成・達成を知らせる投稿を表示
    # 1つだから[0]
    tweet = db.execute("SELECT * FROM tweets WHERE id = ?", tweet_id)[0]
    #ツイートIDからいいね数を取得
    good_count=db.execute("SELECT count(id) FROM favorites WHERE tweet_id = ?",tweet['id'])[0]['count(id)']
    tweet['good_count'] = good_count
    #ツイートIDからコメント数取得
    comment_count=db.execute("SELECT count(id) FROM comments WHERE tweet_id = ?  AND is_deleted = 0",tweet['id'])[0]['count(id)']
    tweet['comment_count'] = comment_count
    #アカウント名を取得
    user=db.execute("SELECT account_name,name FROM users WHERE id = ?",tweet['user_id'])
    account_name=user[0]['account_name']
    tweet['account_name'] = account_name
    #ユーザーネームを取得
    user_name=user[0]['name']
    tweet['user_name']=user_name
    #自分がいいねしてるかを取得(してなかったら0,してたら1)
    good=db.execute("SELECT count(id) FROM favorites WHERE tweet_id = ? AND user_id = ?",tweet['id'],session["user_id"])[0]['count(id)']
    tweet['good']=good


    ##コメントに関する処理
    # 必要な情報をテーブルから引っ張ってくる
    comments = db.execute(
        """
        SELECT c.id AS id, content, c.created_at AS created_at, user_id, name AS user_name, account_name, icon
        FROM comments AS c
        JOIN users AS u ON c.user_id = u.id
        WHERE c.tweet_id = ?
        AND is_deleted = 0
        ORDER BY c.created_at desc
        """
        , tweet_id)
    # アイコンの取得
    tweet['user_icon'] = db.execute("SELECT icon FROM users WHERE id = ?", tweet['user_id'])[0]['icon']


    return render_template("/home/comment.html",tweet=tweet, comments=comments,layout_icon=layout_icon)



# コメントの削除
@app.route("/delete/comment/<int:comment_id>")
# @login_required
def delete_comment(comment_id):
    #削除フラグを立てる
    db.execute("UPDATE comments SET is_deleted = ? WHERE id = ?",1,comment_id)
    tweet_id = db.execute('SELECT tweet_id FROM comments WHERE id = ?', comment_id)[0]['tweet_id']
    return redirect(url_for('comment',tweet_id=tweet_id))


# comment画面でコメントを入力するフォーム
@app.route("/add/comment/<int:tweet_id>",methods=['POST'])
def add_comment(tweet_id):

    if request.method == "POST":
        content = request.form.get("content")
        # コメントの作成時間を取得
        created_time=datetime.datetime.now()+datetime.timedelta(hours=9)
        created_at=created_time.strftime("%Y/%m/%d %H:%M:%S")
        #コメント内容等をデータベースに保存（Insert）
        db.execute("INSERT INTO comments (content,created_at,tweet_id,user_id) VALUES(?,?,?,?)",content,created_at,tweet_id,session['user_id'])

    return redirect(url_for('comment', tweet_id=tweet_id))


#post&comment画面
@app.route("/post_comment/<int:id>")
@login_required
def post_comment(id):
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]
    #フォローしてる人一覧から、ツイート情報を取得
    login_user=session["user_id"]
    #プロフィールのユーザー
    profile_id = id

    #プロフィール表示するのユーザー情報の取得
    profile = db.execute("SELECT id,name AS user_name, account_name, icon FROM users WHERE id = ?", profile_id)[0]

    #フォロー、フォロワー数を追加
    profile["following_count"] = db.execute("SELECT count(id) FROM relations WHERE followed_id = ?", profile_id)[0]['count(id)']
    profile["followers_count"] = db.execute("SELECT count(id) FROM relations WHERE following_id = ?", profile_id)[0]['count(id)']

    # todo、doneの数を取得する
    profile["todo_count"] = db.execute("SELECT count(id) FROM tasks WHERE is_completed != ? and is_deleted = ? and user_id = ?", 1, 0, profile_id)[0]['count(id)']
    profile["done_count"] = db.execute("SELECT count(id) FROM tasks WHERE is_completed = ? and user_id = ?", 1, profile_id)[0]['count(id)']

    tweets = db.execute("SELECT * FROM tweets WHERE user_id = ? AND is_deleted = 0 ORDER BY created_at DESC",id)
    for tweet in tweets:
        #ツイートIDからいいね数を取得
        good_count=db.execute("SELECT count(id) FROM favorites WHERE tweet_id = ?",tweet['id'])[0]['count(id)']
        tweet['good_count'] = good_count
        #ツイートIDからコメント数取得
        comment_count=db.execute("SELECT count(id) FROM comments WHERE tweet_id = ? AND is_deleted = 0",tweet['id'])[0]['count(id)']
        tweet['comment_count'] = comment_count
        #アカウント名を取得
        user=db.execute("SELECT account_name,name FROM users WHERE id = ?",tweet['user_id'])
        account_name=user[0]['account_name']
        tweet['account_name'] = account_name
        #ユーザーネームを取得
        name=user[0]['name']
        tweet['name']=name
        #自分がいいねしてるかを取得(してなかったら0,してたら1)
        good=db.execute("SELECT count(id) FROM favorites WHERE tweet_id = ? AND user_id = ?",tweet['id'],login_user)[0]['count(id)']
        tweet['good']=good
        # アイコンの取得
        tweet['user_icon'] = db.execute("SELECT icon FROM users WHERE id = ?", tweet['user_id'])[0]['icon']

    return render_template("home/profile/post_comment.html",tweets=tweets,login_user=login_user,profile=profile,layout_icon=layout_icon)


@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    # レイアウトのアイコン取得
    layout_icon = db.execute("SELECT icon FROM users WHERE id = ?", session["user_id"])[0]
    if request.method == "POST":

        file = request.files['file']
        account_name = request.form.get("account_name")

        filename= None

        if file and allowed_file(file.filename):
            # 危険な文字を削除（サニタイズ処理）
            filename_secure = secure_filename(file.filename)
            # このファイル名から拡張子の抽出
            root, ext = os.path.splitext(filename_secure)
            # heicの場合はjpegにしてしまう
            # if ext == 'heic':
            #     ext = 'jpeg'
            # uuidの生成
            _uuid = str(uuid.uuid4())
            # ファイル名をuuidに変更する
            filename = "images/" + _uuid + ext
            # ファイルの保存
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        if filename:
            if account_name:
                db.execute("UPDATE users SET account_name = ?, icon = ? WHERE id = ?", account_name, filename, session["user_id"])
            else:
                db.execute("UPDATE users SET icon = ? WHERE id = ?",filename, session["user_id"])
        else:
            if account_name:
                db.execute("UPDATE users SET account_name = ? WHERE id = ?", account_name, session["user_id"])

        return redirect(url_for('todo', id=session["user_id"]))

    else:
        profile_id=session["user_id"]

        profile = db.execute("SELECT id,name AS user_name, account_name, icon FROM users WHERE id = ?", profile_id)[0]

        return render_template("home/profile/edit_profile.html", profile=profile,layout_icon=layout_icon)