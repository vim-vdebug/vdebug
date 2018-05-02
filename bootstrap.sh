#/bin/bash -e
# Hostname
hostname vdebug
echo vdebug > /etc/hostname

# Set password to 'vdebug'
echo "vagrant:vdebug" | chpasswd

# Allow passwordless sudo
if grep "vagrant" /etc/sudoers
then
    echo "vagrant group already a sudoer"
else
    echo "%vagrant ALL=(ALL) NOPASSWD:ALL"
fi

# Install packages
apt-get update
apt-get install locales-all git-core vim vim-gtk xvfb php5 php5-cli php5-xdebug -y

# Fix locale
/usr/sbin/update-locale LANG=en_US LC_ALL=en_US

# Install ruby (http://blog.packager.io/post/101342252191/one-liner-to-get-a-precompiled-ruby-on-your-own)
curl -s https://s3.amazonaws.com/pkgr-buildpack-ruby/current/debian-7/ruby-2.1.5.tgz -o - | sudo tar xzf - -C /usr/local
gem install bundler

cat <<'EOF' >> /etc/php5/conf.d/*-xdebug.ini
xdebug.remote_enable=on
xdebug.remote_handler=dbgp
xdebug.remote_host=localhost
xdebug.remote_port=9000
EOF

cat <<'EOF' > /usr/local/bin/php-xdebug
#!/bin/bash
export XDEBUG_CONFIG="idekey=vdebug"
/usr/bin/env php "$@"
EOF

cat <<'EOF' > /etc/init.d/xvfb
XVFB=/usr/bin/Xvfb
XVFBARGS=":0 -screen 0 1280x1024x24 -ac +extension GLX +render -noreset"
PIDFILE=/var/run/xvfb.pid
case "$1" in
  start)
    echo -n "Starting virtual X frame buffer: Xvfb"
    /sbin/start-stop-daemon --start --quiet --pidfile $PIDFILE --make-pidfile --background --exec $XVFB -- $XVFBARGS
    echo "."
    ;;
  stop)
    echo -n "Stopping virtual X frame buffer: Xvfb"
    /sbin/start-stop-daemon --stop --quiet --pidfile $PIDFILE
    echo "."
    ;;
  restart)
    $0 stop
    $0 start
    ;;
  *)
        echo "Usage: /etc/init.d/xvfb {start|stop|restart}"
        exit 1
esac

exit 0
EOF

chmod +x /etc/init.d/xvfb
update-rc.d xvfb defaults
/etc/init.d/xvfb start

chmod +x /usr/local/bin/php-xdebug

cat <<EOF > /home/vagrant/.vimrc
set nocompatible
filetype off

"<Leader> key is ,
let mapleader=","

" Vundle init
set rtp+=~/.vim/bundle/Vundle.vim/

" Require Vundle
try
    call vundle#begin()
catch
    echohl Error | echo "Vundle is not installed." | echohl None
    finish
endtry

Plugin 'gmarik/Vundle.vim'
Plugin 'vim-vdebug/vdebug.git'

call vundle#end()

filetype plugin indent on
syntax enable

"{{{ Settings
set ttyscroll=0
set hidden
set history=1000
set ruler
set ignorecase
set smartcase
set title
set scrolloff=3
set backupdir=~/.vim-tmp,/tmp
set directory=~/.vim-tmp,/tmp
set wrapscan
set visualbell
set backspace=indent,eol,start
"Status line coolness
set laststatus=2
set showcmd
" Search things
set hlsearch
set incsearch " ...dynamically as they are typed.
" Folds
set foldmethod=marker
set wildmenu
set wildmode=list:longest,full
set nohidden
set shortmess+=filmnrxoOt
set viewoptions=folds,options,cursor,unix,slash
set virtualedit=onemore
set shell=bash\ --login
set nocursorcolumn
set nocursorline
syntax sync minlines=256
"Spaces, not tabs
set shiftwidth=4
set tabstop=4
set expandtab
" Line numbers
set relativenumber
"}}}
EOF

chown vagrant:vagrant /home/vagrant/.vimrc
pip install mock

# Do things as the vagrant user
sudo -u vagrant bash << EOF
echo "export LANG=en_US.UTF-8" >> /home/vagrant/.bashrc
echo "export DISPLAY=:0" >> /home/vagrant/.bashrc
mkdir -p /home/vagrant/.vim-tmp /home/vagrant/.vim/bundle
git clone https://github.com/gmarik/Vundle.vim.git ~/.vim/bundle/Vundle.vim
git clone https://github.com/vim-vdebug/vdebug.git ~/.vim/bundle/vdebug
cd /vagrant
bundle install
EOF

### Neovim installation
cat <<EOF > /home/vagrant/neovim.sh
### This script compiles and builds neovim 
# Install required build tools
sudo apt-get install pkg-config build-essential libtool automake software-properties-common python-dev -y

# install latest cmake
# Taken from https://askubuntu.com/questions/355565/how-to-install-latest-cmake-version-in-linux-ubuntu-from-command-line
#  Uninstall the default version provided by Ubuntu's package manager:
sudo apt-get purge cmake -y
# Go to the official CMake webpage, then download and extract the latest version.
cd /tmp
wget https://cmake.org/files/v3.9/cmake-3.9.4.tar.gz
tar -xzvf cmake-3.9.4.tar.gz
cd cmake-3.9.4/
# Install the extracted source by running:
./bootstrap
make -j4
sudo make install

# Install the neovim itself
cd ~ && git clone https://github.com/neovim/neovim.git && cd neovim
make CMAKE_EXTRA_FLAGS="-DCMAKE_INSTALL_PREFIX=$(echo ~vagrant)/neovim"
make install

# install neovim-python client
sudo pip install neovim

# Set ide key
echo PATH="$(echo ~vagrant)/neovim/build/bin:$PATH" | sudo tee -a /etc/profile
alias nvim="nvim -u ~/.vimrc"
EOF

chown vagrant:vagrant /home/vagrant/neovim.sh
chmod +x /home/vagrant/neovim.sh
