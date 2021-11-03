$(function(){
 console.log("あいうえお");
    $('.js-follow-btn').click(function(e){
        e.stopPropagation();
        console.log("かきくけこ");
        console.log(e);
        var $this = $(this);
        var number = $this.attr('id');
        var data = JSON.stringify({"user_id":number});
        console.log(data);
        $.ajax({
            type: 'POST',
            url: '/follow_unfollow',
            data: data,
            contentType:'application/json',
        }).done(function(data){
            console.log('成功');
            
             // フォローした場合(1)、フォロー解除した場合(0)  
            var login_user = JSON.parse(data["values"]);
            if (login_user["is_followed"]) {
                $("#"+number).html("Following");
                $this.removeClass('btn-success');
                $this.addClass('btn-outline-success');
                console.log("フォロー");
            } else {
                $("#"+number).html("Follow");
                $this.removeClass('btn-outline-success');
                $this.addClass('btn-success');
                console.log("フォロー解除");
            }
        }).fail(function(msg) {
            console.log('Ajax Error');
        });
    });
});